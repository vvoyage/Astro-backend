import hashlib

from kubernetes import client, config
from app.core.config import settings
from loguru import logger
import yaml
import os
import time

# Создаем логгер с контекстом kubernetes
logger = logger.bind(context="kubernetes")

class KubernetesService:
    """
    Сервис для управления сборкой проектов в Kubernetes.
    """
    
    def __init__(self):
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes configuration")
        
        self.v1 = client.CoreV1Api()
        self.batch_v1 = client.BatchV1Api()

    async def create_build_job(self, user_id: str, project_id: str) -> str:
        """
        Создает Job в Kubernetes для сборки проекта.
        
        Args:
            user_id: ID пользователя
            project_id: ID проекта
            
        Returns:
            str: Имя созданного Job
        """
        # K8s labels must be <=63 chars; build-{user_id}-{project_id} is 79 chars.
        # Use a short deterministic hash instead.
        name_hash = hashlib.md5(f"{user_id}-{project_id}".encode()).hexdigest()[:16]
        job_name = f"build-{name_hash}"
        logger.info("Creating build job: {} (project={}, user={})", job_name, project_id, user_id)
        
        # Сначала проверяем существование старого job
        try:
            old_job = self.batch_v1.read_namespaced_job(
                name=job_name,
                namespace="default"
            )
            
            # Если job существует, удаляем его и ждем завершения удаления
            if old_job:
                logger.info("Found existing job, cleaning up: {}", job_name)
                await self.cleanup_job(job_name)
                
                # Ждем пока job действительно удалится
                max_retries = 10
                for i in range(max_retries):
                    try:
                        self.batch_v1.read_namespaced_job(
                            name=job_name,
                            namespace="default"
                        )
                        logger.debug("Waiting for job deletion... attempt {}/{}", i + 1, max_retries)
                        time.sleep(2)
                    except client.exceptions.ApiException as e:
                        if e.status == 404:  # Not Found - значит job удален
                            logger.info("Old job successfully deleted: {}", job_name)
                            break
                        raise
                else:
                    raise Exception(f"Timeout waiting for job {job_name} to be deleted")
                    
        except client.exceptions.ApiException as e:
            if e.status != 404:  # Игнорируем ошибку "Not Found"
                raise

        # Определяем Job
        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name,
                labels={"app": "astro-builder"}
            ),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={"app": "astro-builder"}
                    ),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="builder",
                                image="node:22",
                                command=["/bin/sh", "-c"],
                                args=["""set -e

# Устанавливаем MinIO Client
apt-get update -qq && apt-get install -y -qq wget
wget -q https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc
chmod +x /usr/local/bin/mc

# Настраиваем MinIO
mc alias set minio http://host.docker.internal:9000 $MINIO_ACCESS_KEY $MINIO_SECRET_KEY

# Проверяем наличие исходников в MinIO
echo "=== Source files in MinIO ==="
mc ls --recursive minio/astro-projects/projects/$USER_ID/$PROJECT_ID/src/

# Чистая рабочая директория (важно: workspace должен быть пустым для create-astro)
WORKDIR=/workspace/$PROJECT_ID
rm -rf "$WORKDIR" && mkdir -p "$WORKDIR"
cd "$WORKDIR"

# Создаём базовый Astro проект
npx --yes create-astro@latest . --template basics --no-install --no-git --yes

# Копируем AI-сгенерированные файлы поверх шаблона
mc cp --recursive minio/astro-projects/projects/$USER_ID/$PROJECT_ID/src/ ./src/

echo "=== Final src/ contents ==="
find src/ -type f | sort

# Устанавливаем зависимости и собираем
npm install
npm run build

echo "=== Build complete, dist/ ==="
ls -la dist/

# Загружаем результат в MinIO
mc cp --recursive dist/ minio/astro-projects/projects/$USER_ID/$PROJECT_ID/build/
echo "=== Upload complete ==="
"""],
                                env=[
                                    client.V1EnvVar(name="USER_ID", value=user_id),
                                    client.V1EnvVar(name="PROJECT_ID", value=project_id),
                                    client.V1EnvVar(
                                        name="MINIO_ACCESS_KEY",
                                        value=settings.MINIO_ACCESS_KEY
                                    ),
                                    client.V1EnvVar(
                                        name="MINIO_SECRET_KEY",
                                        value=settings.MINIO_SECRET_KEY
                                    )
                                ],
                                resources=client.V1ResourceRequirements(
                                    requests={
                                        "cpu": "100m",
                                        "memory": "256Mi"
                                    },
                                    limits={
                                        "cpu": "500m",
                                        "memory": "512Mi"
                                    }
                                ),
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="workspace",
                                        mount_path="/workspace"
                                    )
                                ]
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="workspace",
                                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name="project-storage-pvc"
                                )
                            )
                        ],
                        restart_policy="Never"
                    )
                ),
                backoff_limit=4,
                ttl_seconds_after_finished=300  # Удалять job через 5 минут после завершения
            )
        )
        
        # Создаем новый Job
        try:
            self.batch_v1.create_namespaced_job(
                namespace="default",
                body=job
            )
            logger.info("Successfully created job: {}", job_name)
            return job_name
        except Exception as e:
            logger.error("Error creating job {}: {}", job_name, str(e))
            raise Exception(f"Error creating Kubernetes job: {str(e)}")

    async def get_job_status(self, job_name: str) -> str:
        """
        Получает статус Job.
        
        Returns:
            str: Status (Running, Completed, Failed)
        """
        try:
            job = self.batch_v1.read_namespaced_job_status(
                name=job_name,
                namespace="default"
            )
            
            status = "Running"
            if job.status.succeeded:
                status = "Completed"
            elif job.status.failed and not job.status.active:
                # Только если нет активных подов — job окончательно упал
                status = "Failed"
            
            logger.debug("Job {} status: {}", job_name, status)
            return status
        except Exception as e:
            logger.error("Error getting status for job {}: {}", job_name, str(e))
            raise Exception(f"Error getting job status: {str(e)}")

    async def cleanup_job(self, job_name: str):
        """Удаляет Job и связанные ресурсы"""
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace="default",
                body=client.V1DeleteOptions(
                    propagation_policy="Foreground"
                )
            )
            logger.info("Successfully deleted job: {}", job_name)
        except Exception as e:
            logger.error("Error cleaning up job {}: {}", job_name, str(e))
            raise Exception(f"Error cleaning up job: {str(e)}")

    async def get_pod_logs(self, job_name: str) -> str:
        """Получает логи пода, связанного с job"""
        try:
            # Получаем список подов с меткой job-name
            pods = self.v1.list_namespaced_pod(
                namespace="default",
                label_selector=f"job-name={job_name}"
            )
            
            if not pods.items:
                logger.warning("No pods found for job: {}", job_name)
                return "No pods found"
            
            # Берем последний под
            pod = pods.items[-1]
            logs = self.v1.read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace="default"
            )
            
            logger.debug("Retrieved logs for job {}", job_name)
            return logs
        except Exception as e:
            logger.error("Error getting logs for job {}: {}", job_name, str(e))
            return f"Error getting logs: {str(e)}"
