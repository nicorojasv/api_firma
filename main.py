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

#sentry 
import sentry_sdk
# Bibliotecas de tercero

from fastapi import FastAPI, Request
from xmlrpc.client import ServerProxy, Error as XmlRpcError
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from email.header import decode_header

# Sendgrid para envio de correos 
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


load_dotenv()
# Sentry
sentry_sdk.init(
    dsn=os.getenv("DNS_SENTRY"),

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production,
    traces_sample_rate=1.0,
)

# Cargar variables de entorno desde el archivo .env


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
    return request_id


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


@app.post("/obtener_reference")
def obtener_reference(subject):
    print('subject=', subject)
    # Patrón de expresión regular general
    # pattern = r'\d+\.\d+\.\d+-[A-Z]+_CTTO_\d+' # Contrato "16.038.185-K_CTTO_4959"
    # Expresión regular para extraer el patrón deseado
    # pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}-\d{1,3}_\w+_\d{1,4}\b' # Anexo, Carta Término, Autorización
    pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}-[A-Za-z0-9]+_\w+_\d{1,4}\b' # Contrato, Anexo, Carta Término, Autorización
    
    # Buscar coincidencias en el subject
    matches = re.search(pattern, subject)
    
    # Verificar si se encontró una coincidencia y retornar el reference correspondiente
    if matches:
        reference = matches.group(0)
        print('reference', reference)
        return reference
    else:
        print("No se encontró ningún patrón en el subject.")


@app.post("/obtener_id_documento")
def obtener_id_documento(subject):
    print('subject=', subject)
    pattern = r'(?<=_)\d{1,4}\b'
    
    # Buscar coincidencias en el subject
    matches = re.search(pattern, subject)
    
    # Verificar si se encontró una coincidencia y retornar el id documento correspondiente
    if matches:
        documento = matches.group(0)
        print('documento', documento)
        return documento
    else:
        print("No se encontró ningún patrón en el subject.")


@app.post("/obtener_tipo_archivo")
def obtener_tipo_archivo(subject):
    print('subject=', subject)
    pattern = r'(?<=Firma\s)\w+'  

    match = re.search(pattern, subject)

    if match:
        archivo = match.group(0)  
        print("archivo:", archivo)
        return archivo
    else:
        print("No se encontró ningún patrón en el subject.")


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

        # url_webhook = 'https://webhook.site/bc29f0be-e0cf-44fe-b4a5-06c4b3676cb8'
        # requests.post(url_webhook, data=content)

        match = re.search(r"(?<=name=\"subject\"\r\n\r\n)(.*?)(?=\r\n--xYzZY)", content)

        if match:
            subject = match.group(1)
            print('subject', subject)

        try:
            reference = re.findall(r"\d+\.\d+\.\d+\-\d+_\w+", subject)[0]
            print('reference try ', reference)
        except:
            obtener_reference(subject)
        print('reference', reference)

        archivo = obtener_tipo_archivo(subject)

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

        id_documento = obtener_id_documento(subject)

        # Utilice un diccionario y formato de cadena para el estado del mapeo
        status_mapping = {
            "se firm": "FF",
            "Uno de los signatarios rechaz": "RC",
            "Firma": "FT",
        }
        # Mapear el estado según el contenido del asunto
        for condition, mapped_status in status_mapping.items():
            print('condition y mapped_status ', condition, mapped_status)
            if condition in subject:
                status = mapped_status
                break
        print('status', status)

        # Verifique los datos requeridos y devuelva el error si falta
        if not all([id_documento, status, reference]):
            return {"error": "No se pudo extraer id_documento, status y/o reference del cuerpo del email."}

        if status == 'FF':
            # Construct the payload with descriptive key names and use f-strings for string interpolation
            payload = {
                "tipo_archivo": archivo,
                "documento_id": id_documento,
                "estado_firma": status,
                "reference": reference,
                "documento_pdf": traer_documentos(reference, tipo_documento = 'contrato'),
                "certificado_pdf": traer_documentos(reference, tipo_documento ='certificado'),
            }
        else:
            email_content = content # Obtener el contenido del cuerpo del correo desde la solicitud
            email_subject = subject  # Define el asunto del correo aquí
            sender_email = recipient  # Define el correo del remitente aquí


            send_email_with_sendgrid(sender_email,email_content, email_subject)
            payload = {
                "tipo_archivo": archivo,
                "documento_id": id_documento,
                "estado_firma": status,
                "reference": reference,
                "documento_pdf": None,
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
        traceback.print_exc()
        logging.error(f"Error processing email: {e}")
        return {"error": "Ocurrió un error al procesar el email."}



# Clases
@app.post("/recuperacion_manual")
def recuperacion_manual(data: dict):
    reference = data.get('reference')
    request_id = data.get('request_id')

    try:
        # Construct the payload with descriptive key names and use f-strings for string interpolation
        payload = {
            
            "estado_firma": info(request_id)[0]['state'],
            "reference": reference,
            "documento_pdf": traer_documentos(reference, tipo_documento = 'contrato'),
            "certificado_pdf": traer_documentos(reference, tipo_documento ='certificado'),
        }

        # Envíe la solicitud POST y maneje posibles excepciones
        url_notificaciones = os.getenv("URL_RECUPERACION_MANUAL")
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url_notificaciones, headers=headers, data=json.dumps(payload))
        print('response', response)
        response.raise_for_status()
        print('response último', response)

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
            print('contrato_ids: ', contrato_ids )
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
            # completion_date = fecha de finalización
            return contrato_ids

    except Exception as e:
        print(e)


@app.get("/local")
def local():
    try:
        # FT Firma Contrato 20.098.924-4_CTTO_4905 (Firma Contrato 20.098.924-4_CTTO_4905)
        # content ="""'--xYzZY\r\nContent-Disposition: form-data; name="sender_ip"\r\n\r\n108.163.245.250\r\n--xYzZY\r\nContent-Disposition: form-data; name="to"\r\n\r\n<test@firmatec.xyz>\r\n--xYzZY\r\nContent-Disposition: form-data; name="subject"\r\n\r\nFirma Contrato 20.098.924-4_CTTO_4905\r\n--xYzZY\r\nContent-Disposition: form-data; name="envelope"\r\n\r\n{"to":["test@firmatec.xyz"],"from":"nrojas@empresasintegra.cl"}\r\n--xYzZY\r\nContent-Disposition: form-data; name="spam_score"\r\n\r\n2.3\r\n--xYzZY\r\nContent-Disposition: form-data; name="spam_report"\r\n\r\nSpam detection software, running on the system "parsley-p1iad2-spamassassin-668d5659bf-f65xf",\nhas NOT identified this incoming email as spam.  The original\nmessage has been attached to this so you can view it or label\nsimilar future email.  If you have any questions, see\nthe administrator of that system for details.\n\nContent preview:  \n\nContent analysis details:   (2.3 points, 5.0 required)\n\n pts rule name              description\n---- ---------------------- --------------------------------------------------\n 0.0 URIBL_BLOCKED          ADMINISTRATOR NOTICE: The query to URIBL was\n 0.0 RCVD_IN_ZEN_BLOCKED    RBL: ADMINISTRATOR NOTICE: The query to\n 0.0 URIBL_ZEN_BLOCKED      ADMINISTRATOR NOTICE: The query to\n 0.0 HTML_MESSAGE           BODY: HTML included in message\n 0.1 MIME_HTML_MOSTLY       BODY: Multipart message mostly text/html MIME\n-0.1 DKIM_VALID_AU          Message has a valid DKIM or DK signature from\n 0.1 DKIM_SIGNED            Message has a DKIM or DK signature, not necessarily\n-0.1 DKIM_VALID             Message has at least one valid DKIM or DK signature\n 2.3 EMPTY_MESSAGE          Message appears to have no textual parts\n 0.0 TVD_SPACE_RATIO        No description available.\n\r\n--xYzZY\r\nContent-Disposition: form-data; name="email"\r\n\r\nReceived: from arrow.direcnode.com (mxd [108.163.245.250]) by mx.sendgrid.net with ESMTP id JzyvEQCSRmuaiDNb73eA3g for <test@firmatec.xyz>; Fri, 15 Mar 2024 19:05:13.908 +0000 (UTC)\r\nDKIM-Signature: v=1; a=rsa-sha256; q=dns/txt; c=relaxed/relaxed;\r\n\td=empresasintegra.cl; s=default; h=Content-Type:MIME-Version:Message-ID:Date:\r\n\tSubject:To:From:Sender:Reply-To:Cc:Content-Transfer-Encoding:Content-ID:\r\n\tContent-Description:Resent-Date:Resent-From:Resent-Sender:Resent-To:Resent-Cc\r\n\t:Resent-Message-ID:In-Reply-To:References:List-Id:List-Help:List-Unsubscribe:\r\n\tList-Subscribe:List-Post:List-Owner:List-Archive;\r\n\tbh=uIS/idfGclqHlHJdpsI4rjMe0Gf4tPOpelS/nftBhcw=; b=Tyon7u5p0qzS+ycAILj3fEMEsj\r\n\t6ZVpNNylLH/V1/arJLmSbelXz0YHB+bLiyPK1uSscRXSKR8G2HM/wfEtxkW2T3Z5vi0yjw4H6wHJl\r\n\tLbpKUOEvf0LIN/wnnq+bpQcAzEQNJdYbh4bL1LIvha4Ycr5mIuHSZcBiyQpKPTNrVoLBcs1YDaykp\r\n\tvFwuuttQblyNYyyMW+Hq3hIOWv8U9srjWEU6MG8mTS2ZUyZQ9amQ6VC09S0nqvEXBvge9zwk2t3R7\r\n\twnZpsmFBsXgkZOnnXb9YBO5uomPAVHTgiPx0aCA2+KSoDvUHPPA8z1rH1Od0Bkg7a0S4Pl02jwqVN\r\n\tNX7ItaYA==;\r\nReceived: from [186.10.15.27] (port=63952 helo=Ntintegra0054)\r\n\tby arrow.direcnode.com with esmtpsa  (TLS1.2) tls TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384\r\n\t(Exim 4.96.2)\r\n\t(envelope-from <nrojas@empresasintegra.cl>)\r\n\tid 1rlCrf-006t0Z-1w\r\n\tfor test@firmatec.xyz;\r\n\tFri, 15 Mar 2024 16:05:11 -0300\r\nFrom: "Nicolas Rojas" <nrojas@empresasintegra.cl>\r\nTo: <test@firmatec.xyz>\r\nSubject: Firma Contrato 20.098.924-4_CTTO_4905\r\nDate: Fri, 15 Mar 2024 16:05:09 -0300\r\nMessage-ID: <00a901da770b$b425e960$1c71bc20$@empresasintegra.cl>\r\nMIME-Version: 1.0\r\nContent-Type: multipart/alternative;\r\n\tboundary="----=_NextPart_000_00AA_01DA76F2.8ED8FF80"\r\nX-Mailer: Microsoft Outlook 16.0\r\nThread-Index: Adp3C7EUqAAGmGkeTw+giqyI7td6wQ==\r\nContent-Language: es-cl\r\nX-YourOrg-MailScanner-Information: Please contact the ISP for more information\r\nX-YourOrg-MailScanner-ID: 1rlCrf-006t0Z-1w\r\nX-YourOrg-MailScanner: Found to be clean\r\nX-YourOrg-MailScanner-SpamCheck: \r\nX-YourOrg-MailScanner-From: nrojas@empresasintegra.cl\r\nX-Spam-Status: No\r\nX-AntiAbuse: This header was added to track abuse, please include it with any abuse report\r\nX-AntiAbuse: Primary Hostname - arrow.direcnode.com\r\nX-AntiAbuse: Original Domain - firmatec.xyz\r\nX-AntiAbuse: Originator/Caller UID/GID - [47 12] / [47 12]\r\nX-AntiAbuse: Sender Address Domain - empresasintegra.cl\r\nX-Get-Message-Sender-Via: arrow.direcnode.com: authenticated_id: nrojas@empresasintegra.cl\r\nX-Authenticated-Sender: arrow.direcnode.com: nrojas@empresasintegra.cl\r\nX-Source: \r\nX-Source-Args: \r\nX-Source-Dir: \r\n\r\nThis is a multipart message in MIME format.\r\n\r\n------=_NextPart_000_00AA_01DA76F2.8ED8FF80\r\nContent-Type: text/plain;\r\n\tcharset="us-ascii"\r\nContent-Transfer-Encoding: 7bit\r\n\r\n \r\n\r\n\r\n------=_NextPart_000_00AA_01DA76F2.8ED8FF80\r\nContent-Type: text/html;\r\n\tcharset="us-ascii"\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n<html xmlns:v=3D"urn:schemas-microsoft-com:vml" =\r\nxmlns:o=3D"urn:schemas-microsoft-com:office:office" =\r\nxmlns:w=3D"urn:schemas-microsoft-com:office:word" =\r\nxmlns:m=3D"http://schemas.microsoft.com/office/2004/12/omml" =\r\nxmlns=3D"http://www.w3.org/TR/REC-html40"><head><META =\r\nHTTP-EQUIV=3D"Content-Type" CONTENT=3D"text/html; =\r\ncharset=3Dus-ascii"><meta name=3DGenerator content=3D"Microsoft Word 15 =\r\n(filtered medium)"><style><!--\r\n/* Font Definitions */\r\n@font-face\r\n\t{font-family:"Cambria Math";\r\n\tpanose-1:2 4 5 3 5 4 6 3 2 4;}\r\n@font-face\r\n\t{font-family:Aptos;}\r\n/* Style Definitions */\r\np.MsoNormal, li.MsoNormal, div.MsoNormal\r\n\t{margin:0cm;\r\n\tfont-size:12.0pt;\r\n\tfont-family:"Aptos",sans-serif;\r\n\tmso-ligatures:standardcontextual;\r\n\tmso-fareast-language:EN-US;}\r\nspan.EstiloCorreo17\r\n\t{mso-style-type:personal-compose;\r\n\tfont-family:"Aptos",sans-serif;\r\n\tcolor:windowtext;}\r\n.MsoChpDefault\r\n\t{mso-style-type:export-only;\r\n\tmso-fareast-language:EN-US;}\r\n@page WordSection1\r\n\t{size:612.0pt 792.0pt;\r\n\tmargin:70.85pt 3.0cm 70.85pt 3.0cm;}\r\ndiv.WordSection1\r\n\t{page:WordSection1;}\r\n--></style><!--[if gte mso 9]><xml>\r\n<o:shapedefaults v:ext=3D"edit" spidmax=3D"1026" />\r\n</xml><![endif]--><!--[if gte mso 9]><xml>\r\n<o:shapelayout v:ext=3D"edit">\r\n<o:idmap v:ext=3D"edit" data=3D"1" />\r\n</o:shapelayout></xml><![endif]--></head><body lang=3DES-CL =\r\nlink=3D"#467886" vlink=3D"#96607D" style=3D\'word-wrap:break-word\'><div =\r\nclass=3DWordSection1><p =\r\nclass=3DMsoNormal><o:p>&nbsp;</o:p></p></div></body></html>\r\n------=_NextPart_000_00AA_01DA76F2.8ED8FF80--\r\n\r\n\r\n--xYzZY\r\nContent-Disposition: form-data; name="charsets"\r\n\r\n{"to":"UTF-8","from":"UTF-8","subject":"UTF-8"}\r\n--xYzZY\r\nContent-Disposition: form-data; name="dkim"\r\n\r\n{@empresasintegra.cl : pass}\r\n--xYzZY\r\nContent-Disposition: form-data; name="SPF"\r\n\r\npass\r\n--xYzZY\r\nContent-Disposition: form-data; name="from"\r\n\r\n"Nicolas Rojas" <nrojas@empresasintegra.cl>\r\n--xYzZY--\r\n'"""
        # FF 20.261.413-2_CTTD_4941 se firmó (21.011.353-3_CTTD_4948 se firm√≥)
        content ="""'--xYzZY\r\nContent-Disposition: form-data; name="email"\r\n\r\nReceived: from arrow.direcnode.com (mxd [108.163.245.250]) by mx.sendgrid.net with ESMTP id OQlNOcDaTbObEGoA0LmNRw for <test@firmatec.xyz>; Fri, 15 Mar 2024 18:44:40.663 +0000 (UTC)\r\nDKIM-Signature: v=1; a=rsa-sha256; q=dns/txt; c=relaxed/relaxed;\r\n\td=empresasintegra.cl; s=default; h=Content-Type:MIME-Version:Message-ID:Date:\r\n\tSubject:To:From:Sender:Reply-To:Cc:Content-Transfer-Encoding:Content-ID:\r\n\tContent-Description:Resent-Date:Resent-From:Resent-Sender:Resent-To:Resent-Cc\r\n\t:Resent-Message-ID:In-Reply-To:References:List-Id:List-Help:List-Unsubscribe:\r\n\tList-Subscribe:List-Post:List-Owner:List-Archive;\r\n\tbh=yXF0Gr10NxuZui2/RRHSD0rizMRVXvy0PuD5ULrZba8=; b=DYl09jnVO6zo3fIgEvgKo2A7xG\r\n\tOhToUPDujU7ChqfhbZqm4Eu+VNA2BswjLdhAuEuiZ3XLoMe2gxBscFvSEouQYWO0klgDwvoRjldfF\r\n\tiJJyQacIjqTW/TnYCUKPxBN8Tvowoo6VlAGb59knHm44l8KI6SqXdWpRpxm5qGkPLErY3/jBfkfti\r\n\t3mRt+6+gkUzPZKm6C/nh6T0Lbsbgm8X0GgqbVA53fRoIgI4MWNEuYicdDoeeJhqLYudJg44k+7PSq\r\n\tQf1HRNlKMLD5vDMIwU4CpIatrB5vICbBmv57PH7mx/erfXw6ukg90I1Ot7aGE/8Ymu90E41V3GOrz\r\n\tetUfdP/w==;\r\nReceived: from [186.10.15.27] (port=63306 helo=Ntintegra0054)\r\n\tby arrow.direcnode.com with esmtpsa  (TLS1.2) tls TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384\r\n\t(Exim 4.96.2)\r\n\t(envelope-from <nrojas@empresasintegra.cl>)\r\n\tid 1rlCXf-006qAc-1c\r\n\tfor test@firmatec.xyz;\r\n\tFri, 15 Mar 2024 15:44:31 -0300\r\nFrom: "Nicolas Rojas" <nrojas@empresasintegra.cl>\r\nTo: <test@firmatec.xyz>\r\nSubject: =?iso-8859-1?Q?21.011.353-3=5FCTTD=5F4948_se_firm=F3?=\r\nDate: Fri, 15 Mar 2024 15:44:29 -0300\r\nMessage-ID: <008e01da7708$d0fd8410$72f88c30$@empresasintegra.cl>\r\nMIME-Version: 1.0\r\nContent-Type: multipart/alternative;\r\n\tboundary="----=_NextPart_000_008F_01DA76EF.ABB07320"\r\nX-Mailer: Microsoft Outlook 16.0\r\nThread-Index: Adp3CM/EMQBqnxfiSl27j+dK9z0K0Q==\r\nContent-Language: es-cl\r\nX-YourOrg-MailScanner-Information: Please contact the ISP for more information\r\nX-YourOrg-MailScanner-ID: 1rlCXf-006qAc-1c\r\nX-YourOrg-MailScanner: Found to be clean\r\nX-YourOrg-MailScanner-SpamCheck: \r\nX-YourOrg-MailScanner-From: nrojas@empresasintegra.cl\r\nX-Spam-Status: No\r\nX-AntiAbuse: This header was added to track abuse, please include it with any abuse report\r\nX-AntiAbuse: Primary Hostname - arrow.direcnode.com\r\nX-AntiAbuse: Original Domain - firmatec.xyz\r\nX-AntiAbuse: Originator/Caller UID/GID - [47 12] / [47 12]\r\nX-AntiAbuse: Sender Address Domain - empresasintegra.cl\r\nX-Get-Message-Sender-Via: arrow.direcnode.com: authenticated_id: nrojas@empresasintegra.cl\r\nX-Authenticated-Sender: arrow.direcnode.com: nrojas@empresasintegra.cl\r\nX-Source: \r\nX-Source-Args: \r\nX-Source-Dir: \r\n\r\nThis is a multipart message in MIME format.\r\n\r\n------=_NextPart_000_008F_01DA76EF.ABB07320\r\nContent-Type: text/plain;\r\n\tcharset="iso-8859-1"\r\nContent-Transfer-Encoding: 7bit\r\n\r\n \r\n\r\n\r\n------=_NextPart_000_008F_01DA76EF.ABB07320\r\nContent-Type: text/html;\r\n\tcharset="iso-8859-1"\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n<html xmlns:v=3D"urn:schemas-microsoft-com:vml" =\r\nxmlns:o=3D"urn:schemas-microsoft-com:office:office" =\r\nxmlns:w=3D"urn:schemas-microsoft-com:office:word" =\r\nxmlns:m=3D"http://schemas.microsoft.com/office/2004/12/omml" =\r\nxmlns=3D"http://www.w3.org/TR/REC-html40"><head><meta =\r\nhttp-equiv=3DContent-Type content=3D"text/html; =\r\ncharset=3Diso-8859-1"><meta name=3DGenerator content=3D"Microsoft Word =\r\n15 (filtered medium)"><style><!--\r\n/* Font Definitions */\r\n@font-face\r\n\t{font-family:"Cambria Math";\r\n\tpanose-1:2 4 5 3 5 4 6 3 2 4;}\r\n@font-face\r\n\t{font-family:Aptos;}\r\n/* Style Definitions */\r\np.MsoNormal, li.MsoNormal, div.MsoNormal\r\n\t{margin:0cm;\r\n\tfont-size:12.0pt;\r\n\tfont-family:"Aptos",sans-serif;\r\n\tmso-ligatures:standardcontextual;\r\n\tmso-fareast-language:EN-US;}\r\nspan.EstiloCorreo17\r\n\t{mso-style-type:personal-compose;\r\n\tfont-family:"Aptos",sans-serif;\r\n\tcolor:windowtext;}\r\n.MsoChpDefault\r\n\t{mso-style-type:export-only;\r\n\tmso-fareast-language:EN-US;}\r\n@page WordSection1\r\n\t{size:612.0pt 792.0pt;\r\n\tmargin:70.85pt 3.0cm 70.85pt 3.0cm;}\r\ndiv.WordSection1\r\n\t{page:WordSection1;}\r\n--></style><!--[if gte mso 9]><xml>\r\n<o:shapedefaults v:ext=3D"edit" spidmax=3D"1026" />\r\n</xml><![endif]--><!--[if gte mso 9]><xml>\r\n<o:shapelayout v:ext=3D"edit">\r\n<o:idmap v:ext=3D"edit" data=3D"1" />\r\n</o:shapelayout></xml><![endif]--></head><body lang=3DES-CL =\r\nlink=3D"#467886" vlink=3D"#96607D" style=3D\'word-wrap:break-word\'><div =\r\nclass=3DWordSection1><p =\r\nclass=3DMsoNormal><o:p>&nbsp;</o:p></p></div></body></html>\r\n------=_NextPart_000_008F_01DA76EF.ABB07320--\r\n\r\n\r\n--xYzZY\r\nContent-Disposition: form-data; name="charsets"\r\n\r\n{"to":"UTF-8","from":"UTF-8","subject":"UTF-8"}\r\n--xYzZY\r\nContent-Disposition: form-data; name="subject"\r\n\r\n21.011.353-3_CTTD_4948 se firm√≥\r\n--xYzZY\r\nContent-Disposition: form-data; name="envelope"\r\n\r\n{"to":["test@firmatec.xyz"],"from":"nrojas@empresasintegra.cl"}\r\n--xYzZY\r\nContent-Disposition: form-data; name="spam_score"\r\n\r\n2.3\r\n--xYzZY\r\nContent-Disposition: form-data; name="spam_report"\r\n\r\nSpam detection software, running on the system "parsley-p1las1-spamassassin-65fbf9c65-xjhmh",\nhas NOT identified this incoming email as spam.  The original\nmessage has been attached to this so you can view it or label\nsimilar future email.  If you have any questions, see\nthe administrator of that system for details.\n\nContent preview:  \n\nContent analysis details:   (2.3 points, 5.0 required)\n\n pts rule name              description\n---- ---------------------- --------------------------------------------------\n 0.0 URIBL_BLOCKED          ADMINISTRATOR NOTICE: The query to URIBL was\n 0.0 RCVD_IN_ZEN_BLOCKED    RBL: ADMINISTRATOR NOTICE: The query to\n 0.0 HTML_MESSAGE           BODY: HTML included in message\n 0.1 MIME_HTML_MOSTLY       BODY: Multipart message mostly text/html MIME\n-0.1 DKIM_VALID_AU          Message has a valid DKIM or DK signature from\n-0.1 DKIM_VALID             Message has at least one valid DKIM or DK signature\n 0.1 DKIM_SIGNED            Message has a DKIM or DK signature, not necessarily\n 0.0 URIBL_ZEN_BLOCKED      ADMINISTRATOR NOTICE: The query to\n 0.0 TVD_SPACE_RATIO        No description available.\n 2.3 EMPTY_MESSAGE          Message appears to have no textual parts\n\r\n--xYzZY\r\nContent-Disposition: form-data; name="dkim"\r\n\r\n{@empresasintegra.cl : pass}\r\n--xYzZY\r\nContent-Disposition: form-data; name="sender_ip"\r\n\r\n108.163.245.250\r\n--xYzZY\r\nContent-Disposition: form-data; name="SPF"\r\n\r\npass\r\n--xYzZY\r\nContent-Disposition: form-data; name="to"\r\n\r\n<test@firmatec.xyz>\r\n--xYzZY\r\nContent-Disposition: form-data; name="from"\r\n\r\n"Nicolas Rojas" <nrojas@empresasintegra.cl>\r\n--xYzZY--\r\n'"""
        # RC Uno de los signatarios rechazó el documento (Firma Contrato 24.916.278-7_CTTD_4845) (subject Uno de los signatarios rechaz√≥ el documento (Firma Contrato 24.916.278-7_CTTD_4845))
        # content ="""'--xYzZY\r\nContent-Disposition: form-data; name="email"\r\n\r\nReceived: from arrow.direcnode.com (mxd [108.163.245.250]) by mx.sendgrid.net with ESMTP id bLogbhWlRDabx8y27c0vgQ for <test@firmatec.xyz>; Fri, 15 Mar 2024 19:07:16.780 +0000 (UTC)\r\nDKIM-Signature: v=1; a=rsa-sha256; q=dns/txt; c=relaxed/relaxed;\r\n\td=empresasintegra.cl; s=default; h=Content-Type:MIME-Version:Message-ID:Date:\r\n\tSubject:To:From:Sender:Reply-To:Cc:Content-Transfer-Encoding:Content-ID:\r\n\tContent-Description:Resent-Date:Resent-From:Resent-Sender:Resent-To:Resent-Cc\r\n\t:Resent-Message-ID:In-Reply-To:References:List-Id:List-Help:List-Unsubscribe:\r\n\tList-Subscribe:List-Post:List-Owner:List-Archive;\r\n\tbh=HKPC8qr7JZp3OVNBX3LU/ooHXK5TIudFYsMoGOcnCm0=; b=louIXnayV0ocEwPg016Hj1n2ff\r\n\t1L2pMHc9V5KWbSTvRzFX8lDMFJG9I/7UbfPJkUW46HhzuyGdF6OeYKI55hrsbl1pI/Y8Ed9Rz3lt0\r\n\tGs4mOPUH8udGQ18xogw26gP5rziOX19QucUuWIyaYeLigRXtYM+qJ2oDRd4Q1d0628qYqgKLItfmi\r\n\t2kRsiUGw2TkQ+7zKhVmGRu37trHbPILOnb+CsaQ5GJcrbwRmbieC5yGUUHtQWD5Bmwo1UdE0ZgZDb\r\n\t6Q/ehbPndrUlSoshdjVoABS3T9EUgI4Pl569qobnNRq+mR4SM6mL5b75tqgPzFDKaNKeJ9hNB9sEJ\r\n\tyCqdoUIg==;\r\nReceived: from [186.10.15.27] (port=64024 helo=Ntintegra0054)\r\n\tby arrow.direcnode.com with esmtpsa  (TLS1.2) tls TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384\r\n\t(Exim 4.96.2)\r\n\t(envelope-from <nrojas@empresasintegra.cl>)\r\n\tid 1rlCtd-006tHy-13\r\n\tfor test@firmatec.xyz;\r\n\tFri, 15 Mar 2024 16:07:13 -0300\r\nFrom: "Nicolas Rojas" <nrojas@empresasintegra.cl>\r\nTo: <test@firmatec.xyz>\r\nSubject: =?iso-8859-1?Q?Uno_de_los_signatarios_rechaz=F3_el_documento_=28Firma_Con?=\r\n\t=?iso-8859-1?Q?trato_24.916.278-7=5FCTTD=5F4845=29?=\r\nDate: Fri, 15 Mar 2024 16:07:11 -0300\r\nMessage-ID: <00b301da770b$fcb44870$f61cd950$@empresasintegra.cl>\r\nMIME-Version: 1.0\r\nContent-Type: multipart/alternative;\r\n\tboundary="----=_NextPart_000_00B4_01DA76F2.D7673780"\r\nX-Mailer: Microsoft Outlook 16.0\r\nThread-Index: Adp3C/qSQdyioWPGR0u377LZNT06ag==\r\nContent-Language: es-cl\r\nX-YourOrg-MailScanner-Information: Please contact the ISP for more information\r\nX-YourOrg-MailScanner-ID: 1rlCtd-006tHy-13\r\nX-YourOrg-MailScanner: Found to be clean\r\nX-YourOrg-MailScanner-SpamCheck: \r\nX-YourOrg-MailScanner-From: nrojas@empresasintegra.cl\r\nX-Spam-Status: No\r\nX-AntiAbuse: This header was added to track abuse, please include it with any abuse report\r\nX-AntiAbuse: Primary Hostname - arrow.direcnode.com\r\nX-AntiAbuse: Original Domain - firmatec.xyz\r\nX-AntiAbuse: Originator/Caller UID/GID - [47 12] / [47 12]\r\nX-AntiAbuse: Sender Address Domain - empresasintegra.cl\r\nX-Get-Message-Sender-Via: arrow.direcnode.com: authenticated_id: nrojas@empresasintegra.cl\r\nX-Authenticated-Sender: arrow.direcnode.com: nrojas@empresasintegra.cl\r\nX-Source: \r\nX-Source-Args: \r\nX-Source-Dir: \r\n\r\nThis is a multipart message in MIME format.\r\n\r\n------=_NextPart_000_00B4_01DA76F2.D7673780\r\nContent-Type: text/plain;\r\n\tcharset="iso-8859-1"\r\nContent-Transfer-Encoding: 7bit\r\n\r\n \r\n\r\n\r\n------=_NextPart_000_00B4_01DA76F2.D7673780\r\nContent-Type: text/html;\r\n\tcharset="iso-8859-1"\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n<html xmlns:v=3D"urn:schemas-microsoft-com:vml" =\r\nxmlns:o=3D"urn:schemas-microsoft-com:office:office" =\r\nxmlns:w=3D"urn:schemas-microsoft-com:office:word" =\r\nxmlns:m=3D"http://schemas.microsoft.com/office/2004/12/omml" =\r\nxmlns=3D"http://www.w3.org/TR/REC-html40"><head><meta =\r\nhttp-equiv=3DContent-Type content=3D"text/html; =\r\ncharset=3Diso-8859-1"><meta name=3DGenerator content=3D"Microsoft Word =\r\n15 (filtered medium)"><style><!--\r\n/* Font Definitions */\r\n@font-face\r\n\t{font-family:"Cambria Math";\r\n\tpanose-1:2 4 5 3 5 4 6 3 2 4;}\r\n@font-face\r\n\t{font-family:Aptos;}\r\n/* Style Definitions */\r\np.MsoNormal, li.MsoNormal, div.MsoNormal\r\n\t{margin:0cm;\r\n\tfont-size:12.0pt;\r\n\tfont-family:"Aptos",sans-serif;\r\n\tmso-ligatures:standardcontextual;\r\n\tmso-fareast-language:EN-US;}\r\nspan.EstiloCorreo17\r\n\t{mso-style-type:personal-compose;\r\n\tfont-family:"Aptos",sans-serif;\r\n\tcolor:windowtext;}\r\n.MsoChpDefault\r\n\t{mso-style-type:export-only;\r\n\tmso-fareast-language:EN-US;}\r\n@page WordSection1\r\n\t{size:612.0pt 792.0pt;\r\n\tmargin:70.85pt 3.0cm 70.85pt 3.0cm;}\r\ndiv.WordSection1\r\n\t{page:WordSection1;}\r\n--></style><!--[if gte mso 9]><xml>\r\n<o:shapedefaults v:ext=3D"edit" spidmax=3D"1026" />\r\n</xml><![endif]--><!--[if gte mso 9]><xml>\r\n<o:shapelayout v:ext=3D"edit">\r\n<o:idmap v:ext=3D"edit" data=3D"1" />\r\n</o:shapelayout></xml><![endif]--></head><body lang=3DES-CL =\r\nlink=3D"#467886" vlink=3D"#96607D" style=3D\'word-wrap:break-word\'><div =\r\nclass=3DWordSection1><p =\r\nclass=3DMsoNormal><o:p>&nbsp;</o:p></p></div></body></html>\r\n------=_NextPart_000_00B4_01DA76F2.D7673780--\r\n\r\n\r\n--xYzZY\r\nContent-Disposition: form-data; name="SPF"\r\n\r\npass\r\n--xYzZY\r\nContent-Disposition: form-data; name="to"\r\n\r\n<test@firmatec.xyz>\r\n--xYzZY\r\nContent-Disposition: form-data; name="subject"\r\n\r\nUno de los signatarios rechaz√≥ el documento (Firma Contrato 24.916.278-7_CTTD_4845)\r\n--xYzZY\r\nContent-Disposition: form-data; name="spam_report"\r\n\r\nSpam detection software, running on the system "parsley-p1iad2-spamassassin-668d5659bf-hpfgs",\nhas NOT identified this incoming email as spam.  The original\nmessage has been attached to this so you can view it or label\nsimilar future email.  If you have any questions, see\nthe administrator of that system for details.\n\nContent preview:  \n\nContent analysis details:   (2.3 points, 5.0 required)\n\n pts rule name              description\n---- ---------------------- --------------------------------------------------\n 0.0 RCVD_IN_ZEN_BLOCKED    RBL: ADMINISTRATOR NOTICE: The query to\n 0.0 URIBL_ZEN_BLOCKED      ADMINISTRATOR NOTICE: The query to\n 0.0 HTML_MESSAGE           BODY: HTML included in message\n 0.1 MIME_HTML_MOSTLY       BODY: Multipart message mostly text/html MIME\n 0.1 DKIM_SIGNED            Message has a DKIM or DK signature, not necessarily\n-0.1 DKIM_VALID             Message has at least one valid DKIM or DK signature\n-0.1 DKIM_VALID_AU          Message has a valid DKIM or DK signature from\n 0.0 URIBL_BLOCKED          ADMINISTRATOR NOTICE: The query to URIBL was\n 2.3 EMPTY_MESSAGE          Message appears to have no textual parts\n\r\n--xYzZY\r\nContent-Disposition: form-data; name="charsets"\r\n\r\n{"to":"UTF-8","from":"UTF-8","subject":"UTF-8"}\r\n--xYzZY\r\nContent-Disposition: form-data; name="dkim"\r\n\r\n{@empresasintegra.cl : pass}\r\n--xYzZY\r\nContent-Disposition: form-data; name="sender_ip"\r\n\r\n108.163.245.250\r\n--xYzZY\r\nContent-Disposition: form-data; name="from"\r\n\r\n"Nicolas Rojas" <nrojas@empresasintegra.cl>\r\n--xYzZY\r\nContent-Disposition: form-data; name="envelope"\r\n\r\n{"to":["test@firmatec.xyz"],"from":"nrojas@empresasintegra.cl"}\r\n--xYzZY\r\nContent-Disposition: form-data; name="spam_score"\r\n\r\n2.3\r\n--xYzZY--\r\n'"""

        match = re.search(r"(?<=name=\"subject\"\r\n\r\n)(.*?)(?=\r\n--xYzZY)", content)

        if match:
            subject = match.group(1)
            print('subject', subject)

        reference = re.findall(r"\d+\.\d+\.\d+\-\d+_\w+", subject)[0]
        print('reference', reference)
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
 


        

        # Extraiga la identificación del sujeto usando una expresión regular más concisa
        id_contrato_regex = re.compile(r"(\d+)(?:_\w+)?_(\d+)")
        id_contrato_match = id_contrato_regex.search(subject)
        id_contrato = id_contrato_match.group(2) if id_contrato_match else None
        print('id_contrato', id_contrato)

        # Utilice un diccionario y formato de cadena para el estado del mapeo
        status_mapping = {
            "se firm": "FF",
            "Uno de los signatarios rechaz": "RC",
            "Firma Contrato": "FT",
        }
        # Mapear el estado según el contenido del asunto
        for condition, mapped_status in status_mapping.items():
            # print('condition y mapped_status ', condition, mapped_status)
            if condition in subject:
                status = mapped_status
                break
        print('status', status)

        # Verifique los datos requeridos y devuelva el error si falta
        if not all([id_contrato, status, reference]):
            return {"error": "No se pudo extraer id_contrato, status y/o reference del cuerpo del email."}

        contrato_pdf = traer_documentos(reference, tipo_documento='contrato') if status == 'FF' else None
        certificado_pdf = traer_documentos(reference, tipo_documento='certificado') if status == 'FF' else None

        if status == 'FT':
            email_content = content # Obtener el contenido del cuerpo del correo desde la solicitud
            email_subject = subject  # Define el asunto del correo aquí
            sender_email = recipient  # Define el correo del remitente aquí


            send_email_with_sendgrid(sender_email,email_content, email_subject)

        payload = {
            "contrato_id": id_contrato,
            "estado_firma": status,
            "reference": reference,
            "contrato_pdf": contrato_pdf,
            "certificado_pdf": certificado_pdf,
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
        print(e)


