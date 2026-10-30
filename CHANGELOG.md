# Cambios

## 2.0.0

Corregido (pendientes reportados):

- Los campos adicionales se perdían al continuar o volver al paso de pago: ahora se guardan en la sesión del carrito y el formulario se rellena con ellos.
- Las respuestas no aparecían en la confirmación: ahora se muestran junto con el nombre del comprobante.
- Las respuestas nunca se guardaban (`execute_payment` intentaba leerlas de un POST que ya no las traía): ahora se guardan en `OrderPayment.info_data` y se muestran al comprador y al organizador.
- Al reintentar o cambiar el pago, el formulario aparecía vacío: ahora se rellena con las respuestas anteriores y muestra el comprobante ya enviado.
- Comprobante mal asociado:
  - con el comprobante opcional, volver a continuar sin elegir el archivo lo borraba;
  - un comprobante nuevo para el mismo pago se ignoraba;
  - el backend siempre mostraba el primer comprobante del pedido, para cualquier pago.

Corregido (otros):

- XSS: las respuestas del comprador se insertaban sin escapar en la página del pedido del backend.
- El editor visual de campos nunca cargaba en el backend; además insertaba las etiquetas como HTML, no separaba las opciones por línea y sobrescribía un JSON inválido. Ahora el JSON se valida al guardar.
- El comprobante solo se guardaba si el navegador llegaba a la página de «completar pago»; ahora se guarda al crear el pedido.
- Compatibilidad:
  - la migración 0001 dependía de una migración que solo existe desde pretix 2026.7;
  - `CachedFile.bind_to_session` no existe antes de pretix 2026;
  - `PLUGIN_LEVEL_EVENT` no existe antes de pretix 2025.5.

  Antes se declaraba compatible con pretix 2024.7.
- Se habían quitado las opciones estándar de pretix para el método de pago (comisiones, fechas de disponibilidad, montos mínimo/máximo, países, canales de venta, texto de factura).
- Imágenes:
  - una imagen de 100 KB podía ocupar ~360 MB de RAM al decodificarse;
  - las fotos de celular quedaban de lado;
  - las fotos MPO se rechazaban;
  - cada envío decodificaba la imagen dos veces.
- Si el formulario se enviaba sin `multipart` (JavaScript bloqueado), el comprobante se perdía sin aviso.
- Los archivos de comprobante quedaban en disco al borrar pedidos de prueba.
- `pretix migrate` avisaba en cada ejecución de cambios sin migrar (tipo del `id`): el plugin fija `AutoField`, igual que su migración.

Nuevo:

- Datos de la cuenta, monto y referencia en el correo del pedido.
- Enlace para que el comprador vea su comprobante.
- Entrada en el historial del pedido al subir un comprobante.
- Datos en la API (`details` del pago).
- Pruebas automáticas en `tests/`.
