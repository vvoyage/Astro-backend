from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/templates", tags=["templates"])