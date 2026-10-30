# Transferencia con comprobante

Plugin no oficial para pretix. Muestra los datos de la cuenta, deja subir el comprobante (PNG o JPG) y pide los campos adicionales que definas (referencia, banco de origen…). El pago queda pendiente hasta que el organizador lo marque como pagado.

No modifica el plugin de transferencia de pretix. No es un producto de pretix GmbH.

Autor: Bryan Tandayamo. Versión 2.0.0. Requiere pretix 2025.7 o superior (probado en 2026.9).

## Cómo funciona

1. En el paso de pago, el comprador ve los datos de la cuenta, sube la imagen y llena los campos adicionales.
2. Si vuelve atrás o cambia de método, sus respuestas siguen ahí y se le indica que ya subió el comprobante: solo sube otro si quiere reemplazarlo.
3. En la confirmación ve sus respuestas y el nombre del comprobante.
4. Al crear el pedido, el comprobante y las respuestas quedan guardados en el pago, aunque cierre la pestaña enseguida.
5. El correo del pedido incluye los datos de la cuenta, el monto y el código de referencia.
6. En su pedido, el comprador ve sus respuestas y su comprobante, y puede reemplazarlo desde «Cambiar método de pago».
7. En el backend, cada pago muestra su propio comprobante (miniatura, clic para verlo completo), la fecha de subida y las respuestas. La subida queda en el historial del pedido.

## Instalar en Docker

Copia este directorio junto al Dockerfile que ya extiende `pretix/standalone:stable` e instálalo en la imagen:

```dockerfile
COPY pretix-transfer-proof /tmp/pretix-transfer-proof
RUN pip3 install --no-cache-dir /tmp/pretix-transfer-proof
```

Reconstruye la imagen, reinicia el servicio y aplica migraciones:

```bash
docker build . -t pretix-festival:local
sudo systemctl restart pretix
docker exec -it pretix.service pretix migrate
```

En el evento: Ajustes → Plugins → Transferencia con comprobante. Después, en Ajustes → Pagos → Transferencia con comprobante, configura los datos de la cuenta, si el comprobante es obligatorio y los campos adicionales. Ahí también están las opciones normales de pretix para cualquier método de pago: comisión, fechas de disponibilidad (por ejemplo, no aceptar transferencias en los últimos días), montos mínimo y máximo, países y canales de venta.

Al actualizar pretix, vuelve a construir la imagen encima de `pretix/standalone:stable` y reinicia. Los comprobantes quedan en el volumen de datos de pretix, en una carpeta que el servidor web de pretix no publica.

### Campos adicionales

Hay un editor visual en la página de ajustes. Por debajo se guarda una lista JSON:

```json
[
  {"label": "Número de referencia", "type": "text", "required": true},
  {"label": "Banco de origen", "type": "choice", "required": true, "options": ["Pichincha", "Guayaquil", "Produbanco"]}
]
```

Al guardar se valida: si el JSON tiene errores, la página lo dice en vez de guardarlo.

## Actualizar desde 1.x

Instala la nueva versión y corre `pretix migrate`. No hay migraciones nuevas, pero la 0001 ahora depende de una migración antigua de pretix, así que ya no falla en versiones anteriores a 2026.7. Los comprobantes y respuestas guardados por la 1.x se siguen mostrando.

## Pruebas

Con pretix instalado en modo desarrollo:

```bash
pip install -e .
pytest tests --ds=pretix.testutils.settings
```

## Licencia y pie de la boletería

Licencia: AGPL-3.0 con los mismos términos adicionales de pretix. El texto está en `LICENSE`.

Si la boletería se usa para eventos de otras personas, el permiso extra de pretix no cubre ese uso. Hay que dejar el pie oficial de pretix y añadir, en el mismo pie, un enlace al repositorio público de este plugin. No quites el enlace que dice que el sitio usa pretix ni el enlace a su código.

Ejemplo:

```text
Gestión de entradas impulsada por pretix (Código fuente). Plugin de transferencia: https://github.com/BJTS2005/pretix-transfer-proof
```

## Límites conocidos

- Solo imágenes PNG o JPG (incluye fotos de celular en formato MPO y archivos `.jfif`). No acepta PDF ni HEIC: si el banco entrega el comprobante en PDF, el comprador debe subir una captura.
- La imagen se reescribe antes de guardarse: se endereza según la orientación de la cámara, se quitan sus metadatos (por ejemplo, la ubicación GPS) y se reduce a 2400 px en su lado más largo.
- Si el producto requiere aprobación, pretix se salta el paso de pago: el comprador sube el comprobante después de la aprobación, desde su pedido.
- pretix vence los pedidos pendientes al terminar el plazo de pago. Revisa los comprobantes a tiempo o amplía el plazo en Ajustes → Pagos.
