from fastapi import FastAPI, Depends, HTTPException, status
from xmlrpc.client import ServerProxy
import datetime
import base64
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

            # DATA
            # Assuming 'Customer' and 'Employee' are the names of roles in your Odoo instance
            customer_role_id = role_mapping.get('Customer')
            employee_role_id = role_mapping.get('Employee')

            # Obtener los SigningParties de los datos recibidos
            signing_parties = data.get('SigningParties')
            print('signing_parties', signing_parties)
            #obtener documento
            documentos = data.get('document')
            subject = data.get('subject')
            print('subject', subject)
            pages = data.get('docPages')
            print('pages', pages)
            # cantidad de paginas del documento
            num_pages = data.get('numberPages')
            print('num_pages', num_pages)           
           
            attachment = {'name': subject, 'datas': documentos, 'type': 'binary'}
            attachment_id = models.execute_kw(db, uid, password, 'ir.attachment', 'create', [attachment])
            print('hola')

            # Crear template
            template_data = {'name': subject,
                                'redirect_url': 'https://portal.firmatec.cl/',
                                'attachment_id': attachment_id,
                                'sign_item_ids': []}
            for firmante in signing_parties:
                # Consultar si el primer socio ya está registrado
                name = firmante.get('name')
                address = firmante.get('address')
                role = firmante.get('legalName')
                partner_data= {'name': name, 'email': address}
                partner_id = models.execute_kw(db, uid, password, 'res.partner', 'search', [[('email', '=', partner_data['email'])]])
                if not partner_id:
                    partner_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [partner_data])
                else:
                    partner_id = partner_id[0]
                if role == 'Trabajador':
                    signature_field_customer = {'type_id':1,'required':True,'name': partner_data['name'], 'page': num_pages, 'responsible_id': employee_role_id ,'posX':0.15,'posY':0.85,'width':0.2,'height':0.1,'required':True}
                    partner_id_1 = partner_id
                else:
                    signature_field_employee = {'type_id':2,'required':True,'name': partner_data['name'], 'page': num_pages,'responsible_id': customer_role_id,'posX':0.7,'posY':0.85,'width':0.2,'height':0.1,'required':True}
                    partner_id_2 = partner_id
                for i in range(num_pages):
                    print('iiii', i)
                    if firmante['posicion'] == 'primera':
                        template_data['sign_item_ids'].append(
                            (0, 0, {'type_id': firmante['signingOrder'], 'required': True, 'name': firmante['name'], 'page': i, 'responsible_id': customer_role_id, 'posX': 0.15, 'posY': 0.85, 'width': 0.2, 'height': 0.1, 'required': True})
                        )
                    elif firmante['posicion'] == 'segunda':
                        template_data['sign_item_ids'].append(
                            (0, 0, {'type_id': firmante['signingOrder'], 'required': True, 'name': firmante['name'], 'page': i, 'responsible_id': employee_role_id, 'posX': 0.7, 'posY': 0.85, 'width': 0.2, 'height': 0.1, 'required': True})
                        )
            template_id = models.execute_kw(db, uid, password, 'sign.template', 'create', [template_data])

            # Validación de días (5)
            validity_date = validity.date()
            validity_date_str = validity_date.strftime('%Y-%m-%d')
            print('validez', validity_date_str)

            # Crear signature request
            request_data = {
                'template_id': template_id,
                'subject': f'	TEST Firma {subject}',
                'reference': 'Contrato',
                'reminder': 1,
                'validity': validity_date_str,
                # 'attachment_ids': [(6, 0, attachment_ids)],  # Utilizar todos los IDs de adjuntos
                'request_item_ids': [
                    (0, 0, {'partner_id': partner_id_1, 'role_id': customer_role_id, 'mail_sent_order': 1}), 
                    (0, 0, {'partner_id': partner_id_2, 'role_id': employee_role_id, 'mail_sent_order': 2}),
                ],
                'message': """<html>
                                <head>
                                    <title>Mi página de ejemplo</title>
                                </head>
                                <body>
                                Aquí va el contenido SGO3 / FirmaTec
                                </body>
                            </html>""",
                'state': 'sent' # shared, sent, signed, refused, canceled, expired

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
