from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/projects", tags=["projects"])