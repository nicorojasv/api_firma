from fastapi import FastAPI, Request, Depends, HTTPException, status
from xmlrpc.client import ServerProxy
import datetime
import base64
import requests
import re
from xmlrpc.client import ServerProxy, Error as XmlRpcError
from PyPDF2 import PdfReader

# Keys de JWT
SECRET_KEY = "WCTi4FvUmr891sNzASFDwi85Ri7gR8a0DSF9d2l59UbDKEMts"
ALGORITHM = "HS256"

# Keys de Odoo
url = 'https://integra12.odoo.com/'
db = 'integra12'
username = 'soporte@empresasintegra.cl'
password = 'MN2o24*'

app = FastAPI()

# Clases
@app.post("/conexion")
def test_odoo(data: dict):
    # print(data)
    try:
        # Authentication in Odoo
        common = ServerProxy('{}/xmlrpc/2/common'.format(url))
        uid = common.authenticate(db, username, password, {})
        validity = datetime.datetime.now() + datetime.timedelta(days=5)

        if uid:
            models = ServerProxy('{}/xmlrpc/2/object'.format(url))
            roles = models.execute_kw(db, uid, password, 'sign.item.role', 'search_read', [[]], {'fields': ['id', 'name']})
            role_mapping = {role['name']: role['id'] for role in roles}

            # Assuming 'Customer' and 'Employee' are the names of roles in your Odoo instance
            customer_role_id = role_mapping.get('Customer')
            employee_role_id = role_mapping.get('Employee')

            # DATA
            # Obtener los SigningParties de los datos recibidos
            signing_parties = data.get('SigningParties')
            print('signing_parties', signing_parties)

            # obtener documento
            documentos = data.get('document')
            subject = data.get('subject')
            print('subject', subject)
            pages = data.get('pages')
            print('pages', pages)

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
            cc_partner_email = 'test@krino.ai'
            cc_partner_id = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('email', '=', cc_partner_email)]])
            if cc_partner_id:
                cc_partner_id = cc_partner_id[0]
            else:
                # Si no existe, puedes decidir cómo manejar este caso
                cc_partner_id = None
            print('cc_partner_id', cc_partner_id)

            # Etiquetas
            # Consultar si el primer socio ya está registrado
            tag = 'Contrato'
            template_tags = models.execute_kw(db, uid, password, 'sign.template.tag', 'search', [[('name', '=', tag)]])
            if not template_tags:
                template_tags = models.execute_kw(db, uid, password, 'sign.template.tag', 'create', [tag])
            else:
                template_tags = template_tags[0]
            print('template_tags', template_tags)


            # Crear attachment
            attachment = {'name': documentos, 'datas': documentos, 'type': 'binary'}
            attachment_id = models.execute_kw(db, uid, password, 'ir.attachment', 'create', [attachment])

            # Crear template
            template_data = {'name': subject, 'redirect_url': 'https://portal.firmatec.cl/', 'attachment_id': attachment_id, 'sign_item_ids': []}

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

            # Validación de días (5)
            validity_date = validity.date()
            validity_date_str = validity_date.strftime('%Y-%m-%d')
            print('validez', validity_date_str)

            # Crear signature request
            request_data = {
                'template_id': template_id,
                'subject': subject,
                'reference': data.get('reference'),
                'reminder': 1,
                'validity': validity_date_str,
                # 'attachment_ids': [(6, 0, attachment_ids)],  # Utilizar todos los IDs de adjuntos
                'request_item_ids': [
                    (0, 0, {'partner_id': partner_id_1, 'role_id': customer_role_id, 'mail_sent_order': 1}), 
                    (0, 0, {'partner_id': partner_id_2, 'role_id': employee_role_id, 'mail_sent_order': 2}),
                ],
                'message': data.get('message'),
                'state': 'sent', # shared, sent, signed, refused, canceled, expired
                'template_tags': [(6, 0, [template_tags])],
                'cc_partner_ids': [(6, 0, [cc_partner_id])],
                'message_partner_ids': [(6, 0, [cc_partner_id])],
                # 'message_follower_ids': [
                #     (0, 0, {'partner_id': cc_partner_id}),
                # ], # 	Seguidores	one2many
                # 'message_ids': cc_partner_id # 	Mensajes	one2many

            }
            request_id = models.execute_kw(db, uid, password, 'sign.request', 'create', [request_data])
            print(request_id)

            response = {
                'template_id': template_id
            }
            return response
        else:
            return {"error": "Autenticación fallida. Verifica tus credenciales."}
    except ConnectionError:
        return {"error": "Error de conexión a Odoo. Verifica la URL."}
    except XmlRpcError as xe:
        return {"error": f"Error en la llamada XML-RPC a Odoo: {xe}"}
    except ValueError as ve:
        return {"error": f"Error de valor: {ve}"}
    except Exception as e:
        return {"error": f"Error desconocido: {str(e)}"}


@app.post("/procesar_email")
async def procesar_email(request: Request):
    # Leemos el cuerpo del request como texto
    body = await request.body()
    
    # Decodificamos el cuerpo para obtener una cadena de texto
    content = body.decode('utf-8', errors='ignore')

    # Buscamos id_contrato en el asunto del correo
    id_contrato_asunto_match = re.search(r"_CTTO_(\d+)", content)
    print('id_contrato_asunto_match', id_contrato_asunto_match)

    # Extraemos los valores si se encontraron las coincidencias
    id_contrato = id_contrato_asunto_match.group(1) if id_contrato_asunto_match else None
    status = "FF" if "se firmó" in content else ("RC" if "rechazó" in content else None)
    print('id_contrato', id_contrato, 'status', status)

    url = 'https://dev.firmatec.cl/firmas/recepcion_documentos_odoo'
    response = requests.request("POST", url)
    print('response', response)

    if not id_contrato or not status:
        return {"error": "No se pudo extraer id_contrato y/o status del contenido del email."}
    print( id_contrato, status)
    return "Email procesado exitosamente."
