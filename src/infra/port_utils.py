"""
Utilidades para gestión de puertos de red.
Permite encontrar puertos disponibles con lógica de incremento personalizado.
"""

import socket

from src.infra.logging import get_logger

logger = get_logger(__name__)


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Comprueba si un puerto está ocupado en el host especificado."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def find_available_port(start_port: int, increment: int = 3, host: str = "127.0.0.1") -> int:
    """
    Busca el primer puerto disponible empezando por start_port e incrementando de a 'increment'.
    Notifica al operador si el puerto base estaba ocupado.
    """
    current_port = start_port

    if not is_port_in_use(current_port, host):
        return current_port

    logger.warning(f"PUERTO_OCUPADO: El puerto {current_port} está en uso. Buscando alternativa...", port=current_port)

    while is_port_in_use(current_port, host):
        current_port += increment

    import sys

    print(
        f"\n[SISTEMA] NOTIFICACIÓN: Puerto {start_port} ocupado. Usando puerto disponible: {current_port}",
        file=sys.stderr,
    )
    logger.info("PUERTO_SELECCIONADO", original=start_port, final=current_port)

    return current_port


if __name__ == "__main__":
    # Script utilitario para ser usado por bash/make
    import logging
    import sys

    # Silenciar logs en stdout para este script específico
    logging.getLogger().handlers = []
    logging.getLogger().addHandler(logging.NullHandler())

    if len(sys.argv) < 2:
        print("Uso: python -m src.infra.port_utils <start_port>", file=sys.stderr)
        sys.exit(1)

    try:
        base_port = int(sys.argv[1])
        print(find_available_port(base_port))
    except ValueError:
        sys.exit(1)
