import asyncio

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser


async def main():
    url = "https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    }

    print("Descargando página de CORFO...")
    async with AsyncSession(impersonate="chrome120") as session:
        resp = await session.get(url, headers=headers, timeout=30)
        print(f"Status: {resp.status_code}, Length: {len(resp.text)}")
        html = resp.text

    tree = HTMLParser(html)

    # Imprimir todos los selectores de contenedores probables
    print("\n--- Analizando elementos HTML ---")

    # Imprimir las clases de los divs que parecen tarjetas de convocatorias
    # Busquemos selectores comunes como .caja, .resultado, .card, .convocatoria, .item
    class_frequency = {}
    for node in tree.css("div[class]"):
        classes = node.attributes.get("class", "").split()
        for cls in classes:
            class_frequency[cls] = class_frequency.get(cls, 0) + 1

    print("Frecuencia de clases de Divs (Top 20):")
    sorted_classes = sorted(class_frequency.items(), key=lambda x: x[1], reverse=True)
    for cls, freq in sorted_classes[:20]:
        print(f"  .{cls}: {freq}")

    # Busquemos específicamente palabras clave como "Biobío" en texto y veamos sus contenedores padres
    print("\n--- Buscando Biobío en el DOM ---")
    nodes_with_bio = []
    for node in tree.css("p, span, h1, h2, h3, h4, h5, h6, a, div"):
        text = node.text(strip=True)
        if "bio" in text.lower() or "bío" in text.lower():
            nodes_with_bio.append(node)

    print(f"Se encontraron {len(nodes_with_bio)} nodos que contienen la palabra 'bio' o 'bío'.")
    for idx, node in enumerate(nodes_with_bio[:10]):
        parent_tag = node.parent.tag if node.parent else "None"
        parent_class = node.parent.attributes.get("class", "") if node.parent else ""
        print(f"Node #{idx}: Tag=<{node.tag}>, Parent=<{parent_tag} class='{parent_class}'>")
        print(f"  Texto: {node.text(strip=True)[:100]}")

    # Escribir el HTML a un archivo local temporal para inspección manual si es necesario
    with open("corfo_raw.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\nHTML crudo guardado en 'corfo_raw.html'")

if __name__ == "__main__":
    asyncio.run(main())
