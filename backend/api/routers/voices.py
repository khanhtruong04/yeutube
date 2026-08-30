from fastapi import APIRouter

from ...voices import registry

router = APIRouter(tags=["voices"])


@router.get("/providers")
async def get_providers():
    return registry.available_providers()


@router.get("/voices")
async def get_voices(provider: str):
    return registry.list_voices(provider)
