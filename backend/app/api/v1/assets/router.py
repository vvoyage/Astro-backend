from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/assets", tags=["assets"])