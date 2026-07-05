"""Utilidades de permisos compartidas entre handlers.

Extraído de handlers/admin.py (_is_admin) para reutilizarlo en /ads sin
duplicar la lógica. Comportamiento idéntico al original.
"""

from src.config import settings


def is_admin(user_id: int) -> bool:
    """Verifica si un user_id está en la lista de administradores.

    Args:
        user_id: ID del usuario a verificar

    Returns:
        True si el usuario es admin, False en caso contrario
    """
    admin_ids = settings.get_admin_chat_ids_list()
    return user_id in admin_ids
