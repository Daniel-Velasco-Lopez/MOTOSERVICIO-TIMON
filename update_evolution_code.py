import json

with open(r'C:\Users\CICEM\Documents\Carrera ISIC\ISC 8º\SCC-1012 Inteligencia Artificial\motoservicio-timon\workflows\principal-recepcion.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

js_code = r"""const telefono = $json.telefono;
const respuesta = $json.respuesta;

try {
  const response = await this.helpers.httpRequest({
    method: 'POST',
    url: 'http://evolution:8080/message/sendText/timonws',
    headers: {
      'apikey': process.env.AUTHENTICATION_API_KEY,
      'Content-Type': 'application/json'
    },
    body: {
      number: telefono,
      text: respuesta
    }
  });
  return [{ json: { success: true, categoria: $json.categoria, respuesta: respuesta, evolutionResponse: response } }];
} catch (error) {
  return [{ json: { success: false, categoria: $json.categoria, respuesta: respuesta, error: error.message } }];
}"""

for n in data[0]['nodes']:
    if n['name'] == 'Enviar Respuesta WhatsApp':
        n['parameters']['jsCode'] = js_code
        print('Updated')
        break

with open(r'C:\Users\CICEM\Documents\Carrera ISIC\ISC 8º\SCC-1012 Inteligencia Artificial\motoservicio-timon\workflows\principal-recepcion.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('Saved')
