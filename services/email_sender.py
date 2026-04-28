# services/email_sender.py
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from typing import List, Optional
from pathlib import Path
import mimetypes
import logging

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self, remitente: str, password: str):
        self.remitente = remitente
        self.password = password

    def enviar_correo(
        self,
        destinatarios: List[str],
        asunto: str,
        mensaje: str,
        archivo_adjunto: Optional[Path] = None,
        html: bool = False,
        cid_image: Optional[tuple] = None  # Tuple: (content_id_str, Path)
    ):
        """
        Envía un correo:
        - mensaje: texto o HTML
        - archivo_adjunto: archivo adjunto
        - html: si True, se envía el contenido como HTML
        - cid_image: si se quiere incrustar imagen en HTML, tuple(content_id, Path)
        """
        email = EmailMessage()
        email["From"] = self.remitente
        email["To"] = ", ".join(destinatarios)
        email["Subject"] = asunto

        # Contenido HTML o texto plano
        if html:
            email.add_alternative(mensaje, subtype="html")
        else:
            email.set_content(mensaje)

        # Adjuntar archivo si existe
        if archivo_adjunto and not cid_image:
            with open(archivo_adjunto, "rb") as f:
                mime_type, _ = mimetypes.guess_type(archivo_adjunto)
                maintype, subtype = mime_type.split("/") if mime_type else ("application", "octet-stream")
                email.add_attachment(
                    f.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=archivo_adjunto.name
                )

        # Incrustar imagen en HTML si se pasa cid_image
        if cid_image:
            cid_str, img_path = cid_image
            with open(img_path, "rb") as img_file:
                img_data = img_file.read()
                mime_type, _ = mimetypes.guess_type(img_path)
                maintype, subtype = mime_type.split("/") if mime_type else ("application", "octet-stream")
                email.get_payload()[0].add_related(img_data, maintype=maintype, subtype=subtype, cid=cid_str)

        # Enviar correo
        contexto = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=contexto) as smtp:
                smtp.login(self.remitente, self.password)
                smtp.send_message(email)
            logger.info(f"Correo enviado a {destinatarios}")
        except Exception as e:
            logger.exception(f"Error enviando correo a {destinatarios}: {e}")
            raise
