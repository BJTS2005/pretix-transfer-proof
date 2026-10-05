# Transferencia con comprobante

Plugin no oficial para pretix. Muestra los datos de la cuenta y deja subir un comprobante PNG, JPG o JPEG en el paso de pago. El pago queda pendiente hasta que el organizador lo marque pagado.

No modifica el plugin de transferencia de pretix. No es un producto de pretix GmbH.

Autor: Bryan Tandayamo. Versión 1.0.0.

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

En el evento: Ajustes, Plugins, Transferencia con comprobante. Después en Pagos configura los datos de la cuenta y si el comprobante es obligatorio.

Al actualizar pretix, vuelve a construir la imagen encima de `pretix/standalone:stable` y reinicia. Los comprobantes quedan en el volumen de datos de pretix.

## Licencia y pie de la boletería

Licencia: AGPL-3.0 con los mismos términos adicionales de pretix. El texto está en `LICENSE`.

Si la boletería se usa para eventos de otras personas, el permiso extra de pretix no cubre ese uso. Hay que dejar el pie oficial de pretix y añadir, en el mismo pie, un enlace al repositorio público de este plugin. No quites el enlace que dice que el sitio usa pretix ni el enlace a su código.

Ejemplo, cuando el repo ya exista:

```text
Gestión de entradas impulsada por pretix (Código fuente). Plugin de transferencia: https://github.com/TU-USUARIO/pretix-transfer-proof
```

## Límites conocidos

- Solo PNG, JPG y JPEG. La imagen se reescribe antes de guardarse.
- El comprobante permanente se guarda al confirmar el pago. Si pasa más de un día entre subir la imagen y confirmar, pretix puede borrar el archivo temporal.
- No actives la aprobación obligatoria del producto si quieres guardar el comprobante al crear la orden. Para reservas, deja el comprobante como opcional.
