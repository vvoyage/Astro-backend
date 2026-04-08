import asyncio
import hashlib

from kubernetes import client, config
from app.core.config import settings
from loguru import logger
import yaml
import os

logger = logger.bind(context="kubernetes")


class KubernetesService:
    """Запуск и управление Kubernetes Job'ами для сборки Astro-проектов."""

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
        """Создаёт Kubernetes Job для сборки проекта, возвращает имя job'а."""
        # K8s labels ограничены 63 символами, поэтому используем хеш вместо полного ID
        name_hash = hashlib.md5(f"{user_id}-{project_id}".encode()).hexdigest()[:16]
        job_name = f"build-{name_hash}"
        logger.info("Creating build job: {} (project={}, user={})", job_name, project_id, user_id)
        
        # Если job с таким именем уже существует — чистим его перед созданием нового
        try:
            old_job = self.batch_v1.read_namespaced_job(
                name=job_name,
                namespace=settings.KUBERNETES_NAMESPACE
            )
            
            if old_job:
                logger.info("Found existing job, cleaning up: {}", job_name)
                await self.cleanup_job(job_name)
                
                # Ждём реального удаления, иначе создание нового упадёт с конфликтом
                max_retries = 30   # 30 × 5s = 150s max wait
                for i in range(max_retries):
                    try:
                        self.batch_v1.read_namespaced_job(
                            name=job_name,
                            namespace=settings.KUBERNETES_NAMESPACE
                        )
                        logger.debug("Waiting for job deletion... attempt {}/{}", i + 1, max_retries)
                        await asyncio.sleep(5)
                    except client.exceptions.ApiException as e:
                        if e.status == 404:
                            logger.info("Old job successfully deleted: {}", job_name)
                            break
                        raise
                else:
                    raise Exception(f"Timeout waiting for job {job_name} to be deleted")
                    
        except client.exceptions.ApiException as e:
            if e.status != 404:
                raise

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

# ставим mc (MinIO Client)
apt-get update -qq && apt-get install -y -qq wget
wget -q https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc
chmod +x /usr/local/bin/mc

mc alias set minio $MINIO_URL $MINIO_ACCESS_KEY $MINIO_SECRET_KEY

echo "=== Source files in MinIO ==="
mc ls --recursive minio/astro-projects/projects/$USER_ID/$PROJECT_ID/src/

# workspace должен быть пустым, иначе create-astro ругается
WORKDIR=/workspace/$PROJECT_ID
rm -rf "$WORKDIR" && mkdir -p "$WORKDIR"
cd "$WORKDIR"

npx --yes create-astro@latest . --template basics --no-install --no-git --yes

# кладём AI-сгенерированные файлы поверх дефолтного шаблона
mc cp --recursive minio/astro-projects/projects/$USER_ID/$PROJECT_ID/src/ ./src/

echo "=== Final src/ contents ==="
find src/ -type f | sort

npm install
npm run build

echo "=== Build complete, dist/ ==="
ls -la dist/

mc cp --recursive dist/ minio/astro-projects/projects/$USER_ID/$PROJECT_ID/build/
echo "=== Upload complete ==="
"""],
                                env=[
                                    client.V1EnvVar(name="USER_ID", value=user_id),
                                    client.V1EnvVar(name="PROJECT_ID", value=project_id),
                                    client.V1EnvVar(
                                        name="MINIO_URL",
                                        value=f"{'https' if settings.MINIO_SECURE else 'http'}://{settings.MINIO_ENDPOINT}"
                                    ),
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
                ttl_seconds_after_finished=300  # автоудаление через 5 минут
            )
        )
        
        try:
            self.batch_v1.create_namespaced_job(
                namespace=settings.KUBERNETES_NAMESPACE,
                body=job
            )
            logger.info("Successfully created job: {}", job_name)
            return job_name
        except Exception as e:
            logger.error("Error creating job {}: {}", job_name, str(e))
            raise Exception(f"Error creating Kubernetes job: {str(e)}")

    async def get_job_status(self, job_name: str) -> str:
        """Возвращает статус job'а: Running / Completed / Failed."""
        try:
            job = self.batch_v1.read_namespaced_job_status(
                name=job_name,
                namespace=settings.KUBERNETES_NAMESPACE
            )
            
            status = "Running"
            if job.status.succeeded:
                status = "Completed"
            elif job.status.failed and not job.status.active:
                # считаем failed только когда нет активных подов
                status = "Failed"
            
            logger.debug("Job {} status: {}", job_name, status)
            return status
        except Exception as e:
            logger.error("Error getting status for job {}: {}", job_name, str(e))
            raise Exception(f"Error getting job status: {str(e)}")

    async def cleanup_job(self, job_name: str):
        """Удаляет job и все связанные поды (Foreground propagation)."""
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=settings.KUBERNETES_NAMESPACE,
                body=client.V1DeleteOptions(
                    propagation_policy="Foreground"
                )
            )
            logger.info("Successfully deleted job: {}", job_name)
        except Exception as e:
            logger.error("Error cleaning up job {}: {}", job_name, str(e))
            raise Exception(f"Error cleaning up job: {str(e)}")

    async def get_pod_logs(self, job_name: str) -> str:
        """Возвращает логи последнего пода job'а."""
        try:
            pods = self.v1.list_namespaced_pod(
                namespace=settings.KUBERNETES_NAMESPACE,
                label_selector=f"job-name={job_name}"
            )
            
            if not pods.items:
                logger.warning("No pods found for job: {}", job_name)
                return "No pods found"
            
            pod = pods.items[-1]
            logs = self.v1.read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace=settings.KUBERNETES_NAMESPACE
            )
            
            logger.debug("Retrieved logs for job {}", job_name)
            return logs
        except Exception as e:
            logger.error("Error getting logs for job {}: {}", job_name, str(e))
            return f"Error getting logs: {str(e)}"
