import datetime
import base64
import re
import os

# Módulos de biblioteca estándar

import requests
import json
import logging
import traceback
import sys
import chardet

# Bibliotecas de terceros

from fastapi import FastAPI, Request
from xmlrpc.client import ServerProxy, Error as XmlRpcError
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from email.header import decode_header

# Sendgrid para envio de correos 
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = FastAPI()

# Keys de JWT
secret_key = os.getenv("SECRET_KEY")
algorithm = os.getenv("ALGORITHM")

# Keys de Odoo
url = os.getenv("URL")
db = os.getenv("DB")
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")

# Clases
@app.post("/conexion")
def solicitud_firma(data: dict):
    print('conex')
    """
    Esta función crea una solicitud de firma en Odoo basada en los datos proporcionados.

    Argumentos:
        datos: un diccionario que contiene los datos de la solicitud.
        url: La URL del servidor Odoo.
        db: El nombre de la base de datos de Odoo.
        nombre de usuario: El nombre de usuario para la autenticación de Odoo.
        contraseña: La contraseña para la autenticación de Odoo.

    Devoluciones:
        Un diccionario que contiene el ID de la solicitud o un mensaje de error.
    """
    try:
        # Autenticación en Odoo
        uid = authenticate(url, db, username, password)
        print('bien ')
        if not uid:
            return {"error": "Autenticación fallida. Verifica tus credenciales."}

        models = ServerProxy('{}/xmlrpc/2/object'.format(url))

        signing_parties = data.get('SigningParties')
        print('signing_parties: ',signing_parties)
        # redirect_url = data.get('redirect_url')
        # print('redirect_url: ',redirect_url)
        documentos = data.get('document')
        reference = data.get('reference')
        print('reference: ',reference)
        reminder = data.get('reminder')
        print('reminder: ',reminder)
        message = data.get('message')
        print('message: ',message)
        subject = data.get('subject')
        print('subject: ',subject)
        pages = data.get('pages')
        print('pages: ',pages)
        tag = data.get('tag')
        print('tag: ',tag)

        roles = models.execute_kw(db, uid, password, 'sign.item.role', 'search_read', [[]], {'fields': ['id', 'name']})
        role_mapping = {role['name']: role['id'] for role in roles}

        # 'Cliente' y 'Empleado' son los nombres de los roles en su instancia de Odoo
        customer_role_id = role_mapping.get('Customer')
        employee_role_id = role_mapping.get('Employee')

        partner_ids = create_partners(signing_parties, uid, password, models)
        print('partner_ids: ',partner_ids)
        tag_id = create_tag(tag, uid, password, models)
        print('tag_id: ',tag_id)
        attachment_id = create_attachment(documentos, uid, password, models)
        print('attachment_id: ',attachment_id)
        template_id = create_template(subject, attachment_id, signing_parties, pages, customer_role_id, employee_role_id, uid, password, models)
        print('template_id: ',template_id)
        request_id = create_signature_request(template_id, subject, reference, reminder, partner_ids, customer_role_id, employee_role_id, message, tag_id, uid, password, models)

        return {"request_id": request_id}

    except ConnectionError:
        return {"error": "Error de conexión a Odoo. Verifica la URL."}
    except XmlRpcError as xe:
        return {"error": f"Error en la llamada XML-RPC a Odoo: {xe}"}
    except ValueError as ve:
        return {"error": f"Error de valor: {ve}"}
    except Exception as e:
        return {"error": f"Error desconocido: {str(e)}"}


def authenticate(url, db, username, password):
    print('autent')
    """Se autentica con Odoo y devuelve la identificación del usuario si tiene éxito."""
    common = ServerProxy('{}/xmlrpc/2/common'.format(url))
    uid = common.authenticate(db, username, password, {})

    if not uid:
        raise Exception("Authentication failed")  # Manejar el error de autenticación

    return uid  # Devuelve el uid para un posible almacenamiento en caché


def create_partners(signing_parties, uid, password, models):
    print('partne')
    """Función de creación de partners"""
    try:
        # Create partners
        partner_data_1 = signing_parties[0]
        partner_data_2 = signing_parties[1]

        # Consultar si el primer socio ya está registrado
        partner_id_1 = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('email', '=', partner_data_1['email'])]])
        if not partner_id_1:
            partner_id_1 = models.execute_kw(db, uid, password, 'res.partner', 'create', [partner_data_1])
        else:
            partner_id_1 = partner_id_1[0]

        partner_id_2 = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('email', '=', partner_data_2['email'])]])
        if not partner_id_2:
            partner_id_2 = models.execute_kw(db, uid, password, 'res.partner', 'create', [partner_data_2])
        else:
            partner_id_2 = partner_id_2[0]
        print('firmantes')
        # Obtener el ID del socio con la dirección de correo electrónico 'test@krino.ai'
        cc_partner_email = 'test@firmatec.xyz'
        cc_partner_id = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('email', '=', cc_partner_email)]])
        if cc_partner_id:
            cc_partner_id = cc_partner_id[0]
        else:
            # Si no existe, puedes decidir cómo manejar este caso
            cc_partner_id = None
        print('cc_partner_id', cc_partner_id)
        return [partner_id_1, partner_id_2, cc_partner_id]
    except:
        return {"error": "Faltan signing_parties requeridos en la solicitud."}


def create_tag(tag, uid, password, models):
    print('tag')
    print('tag: ',tag)
    """Función de creación de etiquetas"""
    # Tag management template_tags
    models = ServerProxy('{}/xmlrpc/2/object'.format(url))
    tag_id = models.execute_kw(db, uid, password, 'sign.template.tag', 'search', [[('name', '=', tag)]])
    if not tag_id:
        tag_id = models.execute_kw(db, uid, password, 'sign.template.tag', 'create', [tag])
    else:
        tag_id = tag_id[0]
    print('tag_id', tag_id)
    return tag_id


def create_attachment(documentos, uid, password, models):
    print('attach')
    """Función de creación de attachments"""
    # Crear Attachment
    models = ServerProxy('{}/xmlrpc/2/object'.format(url))
    attachment = {'name': documentos, 'datas': documentos, 'type': 'binary'}
    attachment_id = models.execute_kw(db, uid, password, 'ir.attachment', 'create', [attachment])
    print('creo')
    return attachment_id


def create_template(subject, attachment_id, signing_parties, pages, customer_role_id, employee_role_id, uid, password, models):
    print('templat')
    """Función de creación de templates"""
    # Crear template
    models = ServerProxy('{}/xmlrpc/2/object'.format(url))
    template_data = {'name': subject, 'attachment_id': attachment_id, 'sign_item_ids': []}

    for firmante in signing_parties:
        for page in pages:  # Iterate through the desired pages list
            if firmante['display_name'] == 'Trabajador':
                template_data['sign_item_ids'].append(
                    (0, 0, {'type_id': firmante['color'], 'required': True, 'name': firmante['name'],
                            'page': page, 'responsible_id': customer_role_id, 'posX': 0.15, 'posY': 0.85, 'width': 0.2, 'height': 0.1, 'required': True})
                )
            elif firmante['display_name'] == 'Empleador':
                template_data['sign_item_ids'].append(
                    (0, 0, {'type_id': firmante['color'], 'required': True, 'name': firmante['name'],
                            'page': page, 'responsible_id': employee_role_id, 'posX': 0.7, 'posY': 0.85, 'width': 0.2, 'height': 0.1, 'required': True})
                )

    template_id = models.execute_kw(db, uid, password, 'sign.template', 'create', [template_data])
    print('hola')
    return template_id


def create_signature_request(template_id, subject, reference, reminder, partner_ids, customer_role_id, employee_role_id, message, tag_id, uid, password, models):
    print('signature')
    """Función de creación de requests de firma"""
    # Validación de días (5)
    validity = datetime.datetime.now() + datetime.timedelta(days=5)
    validity_date = validity.date()
    validity_date_str = validity_date.strftime('%Y-%m-%d')
    print('validez', validity_date_str)

    # Crear signature request
    request_data = {
        'template_id': template_id,
        'subject': subject,
        'reference': reference,
        'reminder': reminder,
        'validity': validity_date_str,
        # 'attachment_ids': [(6, 0, attachment_ids)],  # Utilizar todos los IDs de adjuntos
        'request_item_ids': [
            (0, 0, {'partner_id': partner_ids[0], 'role_id': customer_role_id, 'mail_sent_order': 1}), 
            (0, 0, {'partner_id': partner_ids[1], 'role_id': employee_role_id, 'mail_sent_order': 2}),
        ],
        'message': message,
        'state': 'sent', # shared, sent, signed, refused, canceled, expired
        'template_tags': [(6, 0, [tag_id])],
        'cc_partner_ids': [(6, 0, [partner_ids[2]])],
        'message_partner_ids': [(6, 0, [partner_ids[2]])],

    }
    request_id = models.execute_kw(db, uid, password, 'sign.request', 'create', [request_data])
    print(request_id)

    response = {
        'request_id': request_id
    }
    return response


def detect_encoding(body):
    """
    Detecta la codificación del cuerpo del correo electrónico.

    Argumentos:
        body: el cuerpo del correo electrónico.

    Devoluciones:
        La codificación del cuerpo del correo electrónico.
    """
    result = chardet.detect(body)
    return result.get("encoding", "utf-8")


@app.post("/procesar_email")
async def procesar_email(request: Request):
    """
    Esta función procesa una solicitud de correo electrónico y extrae información relevante.
    para enviarlo a la URL especificada.

    Argumentos:
        solicitud: la solicitud de correo electrónico entrante.

    Devoluciones:
        Una respuesta JSON que indica éxito o error.
    """
    try:
        # Leer el cuerpo de la solicitud como texto
        print('procesar_email entro')
        body = await request.body()
        # Decodifica el cuerpo del correo electrónico con la codificación detectada
        encoding = detect_encoding(body)
        content = body.decode(encoding)
        # content = body.decode('utf-8')
        # print('body', body)
        # print('contenidoooo', content)

        # Divide el contenido en líneas y ponlas en minúsculas para que no se distinga entre mayúsculas y minúsculas.
        lines = [line.lower() for line in content.splitlines()]

        # Extraiga el asunto y la referencia en dos pasos combinados utilizando comprensión de listas y cadenas f
        subject = next((line.split(":")[1].strip() for line in lines if line.startswith("subject:")), None)
        if subject is not None:
            # Decodifica la cadena del asunto utilizando la biblioteca `email`
            subject, encoding = decode_header(subject)[0]
            if encoding is not None:
                subject = subject.decode(encoding)
            print('subject', subject)
        reference = re.findall(r"\d+\.\d+\.\d+\-\d+_\w+", subject)[0].upper()
        # Obtener el destinatario
        recipient = None
        for line in content.splitlines():
            if line.lower().startswith("to"):
                match = re.search(r'<([^>]*)>', line)
                if match:
                    recipient = match.group(1)

        # Imprimir los resultados
        if subject and recipient:
            print(f"Asunto: {subject}")
            print(f"Destinatario: {recipient}")
        else:
            print("No se pudo encontrar el asunto o el destinatario.")
 


        email_content = content # Obtener el contenido del cuerpo del correo desde la solicitud
        email_subject = subject  # Define el asunto del correo aquí
        sender_email = recipient  # Define el correo del remitente aquí


        send_email_with_sendgrid(sender_email,email_content, email_subject)

        # Extraiga la identificación del sujeto usando una expresión regular más concisa
        id_contrato_regex = re.compile(r"(\d+)(?:_\w+)?_(\d+)")
        id_contrato_match = id_contrato_regex.search(subject)
        id_contrato = id_contrato_match.group(2) if id_contrato_match else None
        print('id_contrato', id_contrato)

        # Utilice un diccionario y formato de cadena para el estado del mapeo
        status_mapping = {
            "se firm": "FF",
            "uno de los signatarios rechazó el documento": "RC",
            "firma contrato": "FT",
        }
        # Mapear el estado según el contenido del asunto
        for condition, mapped_status in status_mapping.items():
            if condition in subject:
                status = mapped_status
                break
        print('status', status)

        # Verifique los datos requeridos y devuelva el error si falta
        if not all([id_contrato, status, reference]):
            return {"error": "No se pudo extraer id_contrato, status y/o reference del cuerpo del email."}

        if status == 'FF':
            # Construct the payload with descriptive key names and use f-strings for string interpolation
            payload = {
                "contrato_id": id_contrato,
                "estado_firma": status,
                "reference": reference,
                "contrato_pdf": traer_documentos(reference, tipo_documento = 'contrato'),
                "certificado_pdf": traer_documentos(reference, tipo_documento ='certificado'),
            }
        else:
            payload = {
                "contrato_id": id_contrato,
                "estado_firma": status,
                "reference": reference,
                "contrato_pdf": None,
                "certificado_pdf": None,
            }

        # Envíe la solicitud POST y maneje posibles excepciones
        url_notificaciones = os.getenv("URL_NOTIFICACIONES")
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url_notificaciones, headers=headers, data=json.dumps(payload))
        print('response', response)
        response.raise_for_status()
        print('response último', response)

        return "Email procesado exitosamente."

    except Exception as e:
        # Registre el error para depurarlo y devolver una respuesta adecuada
        logging.error(f"Error processing email: {e}")
        return {"error": "Ocurrió un error al procesar el email."}


@app.get("/traer_documentos")
def traer_documentos(reference, tipo_documento):
    print('reference: ', reference )
    try:
        # Autenticación en Odoo
        uid = authenticate(url, db, username, password)

        if uid:
            models = ServerProxy('{}/xmlrpc/2/object'.format(url))
            contrato_ids = models.execute_kw(db, uid, password, 'sign.request', 'search_read', [[('reference', '=', reference)]], {'fields': ['completed_document_attachment_ids']} )
            print ('que trae esto',contrato_ids[0]['completed_document_attachment_ids'])
            
            if contrato_ids:
                certificado = models.execute_kw(db, uid, password, 'ir.attachment', 'search_read', [[('id', '=', contrato_ids[0]['completed_document_attachment_ids'])]], {'fields': ['name', 'datas']})
                # Solo documento firmado en base64
                if tipo_documento == 'certificado':
                    return certificado[0]['datas']
                if tipo_documento == 'contrato':
                    print ('Bien')
                    return certificado[1]['datas']
                else:
                    return {"message": "No se encontraron documentos"}
            else:
                print('No se encontraron documentos')
                return {"message": "No se encontraron documentos"}
    except XmlRpcError as xe:
        traceback.print_exc(file=sys.stderr)
        return {"error": f"Error en la llamada XML-RPC a Odoo: {xe}"}
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return {"error": f"Error desconocido: {e}"}

    return {"message": "Documentos obtenidos exitosamente."}


def send_email_with_sendgrid(sender_email,email_content, email_subject):
    sg = SendGridAPIClient(api_key=os.getenv("API"))          

    email= []
    email.append(sender_email.replace("@firmatec.xyz", "@empresasintegra.cl"))
    email.append('soporte@empresasintegra.cl')
    email.append('maye.yrs23@gmail.com')
    email.append('n.rojas.valdes@gmail.com')


    # Expresión regular para encontrar el texto que deseas
    pattern = r"""text/html; charset="utf-8"\r\nContent-Transfer-Encoding: base64\r\nMIME-Version: 1.0\r\n\r\n(.*?)--"""

    # Buscar el texto que coincida con el patrón en el correo completo
    matches = re.findall(pattern, email_content, re.DOTALL)

    # Si se encuentran coincidencias, almacenarlas en la variable correo_html
    if matches:
        correo_html = matches[0]
    else:
        print("No se encontró el texto deseado en el correo.")

    #base64 a html
    correo_html = base64.b64decode(correo_html).decode('utf-8')

    message = Mail(
        from_email='notificaciones@krino.ai' ,  # Asegúrate de cambiar esto por tu correo registrado en SendGrid
        to_emails= email,  # Destinatario del correo
        subject=f'Reenviado: {email_subject}',
        html_content=correo_html
    )
    try:
        response = sg.send(message)
        print(f"Correo reenviado con éxito. Código de estado: {response.status_code}")
    except Exception as e:
        print(f"Error al enviar correo con SendGrid: {e}")


@app.put("/cancelar")
def cancelar_firma(id):
    print('entro en la funcion de cancelar')
    """
    Cancela una solicitud de firma.
    """
    try:
        # Autenticación en Odoo
        uid = authenticate(url, db, username, password)
        print('bien ')
        if not uid:
            return {"error": "Autenticación fallida. Verifica tus credenciales."}

        models = ServerProxy('{}/xmlrpc/2/object'.format(url))
        # Buscar el registro y obtener su ID y estado
        documento_id = models.execute_kw(db, uid, password, 'sign.request', 'search_read', [[('id', '=', id)]], {'fields': ['id', 'state']})

        # Verificar si se encontró algún registro
        if documento_id:
            # Obtener el estado del documento
            estado = documento_id[0]['state']
            print('state: ', estado )
            
            # Verificar si el estado es 'canceled' o 'signed'
            if estado == 'canceled':
                return {"message": "El documento ya está cancelado."}
            elif estado == 'signed':
                return {"message": "El documento está firmado."}
            else:
                # Actualizar el estado del registro
                models.execute_kw(db, uid, password, 'sign.request', 'write', [documento_id[0]['id'], {'state': 'canceled'}])
                print("El estado del documento ha sido actualizado a 'canceled'.")
                return {"message": "El documento se ha cancelado exitosamente."}
        else:
            print("No se encontró ningún registro con el ID proporcionado.")
            return {"error": "No se encontró el documento con el ID proporcionado."}

    except ConnectionError:
        return {"error": "Error de conexión a Odoo. Verifica la URL."}
    except XmlRpcError as xe:
        return {"error": f"Error en la llamada XML-RPC a Odoo: {xe}"}
    except ValueError as ve:
        return {"error": f"Error de valor: {ve}"}
    except Exception as e:
        return {"error": f"Error desconocido: {str(e)}"}


@app.get("/info")
def info(id):
    try:
        # Autenticación en Odoo
        uid = authenticate(url, db, username, password)
        if uid:
            models = ServerProxy('{}/xmlrpc/2/object'.format(url))
            contrato_ids = models.execute_kw(db, uid, password, 'sign.request', 'search_read', [[('id', '=', id)]], {'fields': ['message_follower_ids', 'message_ids', 'create_date', 'completion_date', 'completed_document_attachment_ids', 'completed_document', 'cc_partner_ids', 'attachment_ids', 'activity_state', 'active', 'write_date', 'validity', 'template_tags', 'template_id', 'subject', 'state', 'start_sign', 'sign_log_ids', 'request_item_ids', 'reminder', 'reference', 'progress', 'nb_wait', 'nb_total', 'nb_closed', 'my_activity_date_deadline', 'message_partner_ids', 'message_is_follower', 'message_ids', 'message_has_sms_error', 'message_has_error_counter', 'message_has_error', 'message_follower_ids', 'message_cc', 'message_attachment_count', 'message', 'last_reminder', 'id', 'has_message', 'favorited_ids', 'display_name']})
            firma = models.execute_kw(db, uid, password, 'sign.request.item', 'search_read', [[('id', '=', contrato_ids[0]['request_item_ids'][0])]], {'fields': ['state']})
            print('firma', firma)
            print('otra', contrato_ids[0]['request_item_ids'])
            print('otra', contrato_ids[0]['request_item_ids'][0])
            print('otra', contrato_ids[0]['request_item_ids'][1])
            return contrato_ids

    except Exception as e:
        print(e)
