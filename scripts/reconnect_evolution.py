"""
Script para reconectar Evolution API a WhatsApp.

Uso:
  python scripts/reconnect_evolution.py          # Muestra QR en terminal
  python scripts/reconnect_evolution.py --pairing # Obtener código de apareamiento
  python scripts/reconnect_evolution.py --status  # Ver estado actual
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import base64

EVOLUTION_API = "http://localhost:8080"
API_KEY = "evotimon2026"
INSTANCE = "timonws"


def request(method, path, body=None):
    url = f"{EVOLUTION_API}{path}"
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": True, "status": e.code, "body": e.read().decode()[:500]}
    except Exception as e:
        return {"error": True, "message": str(e)}


def check_instance():
    print(f"[*] Verificando instancia '{INSTANCE}'...")
    result = request("GET", f"/instance/connectionState/{INSTANCE}")
    if result.get("error"):
        print(f"[!] Instancia no existe o error: {result}")
        return False
    state = result.get("state", {}).get("state") or result.get("state")
    print(f"[+] Estado actual: {state}")
    return True


def create_instance():
    print(f"[*] Creando instancia '{INSTANCE}'...")
    result = request("POST", "/instance/create", {
        "instanceName": INSTANCE,
        "qrcode": True,
        "number": "521",
    })
    if result.get("error") and "already exists" in str(result):
        print("[!] Instancia ya existe")
        return True
    print(f"[+] Instancia creada: {result.get('instance', {}).get('instanceName', 'OK')}")
    return True


def get_qr():
    print(f"[*] Obteniendo QR para '{INSTANCE}'...")
    result = request("GET", f"/instance/qrcode/{INSTANCE}")
    if "base64" in result or "qrcode" in result:
        qr_b64 = result.get("base64") or result.get("qrcode", {}).get("base64")
        if qr_b64:
            with open("qr_code.png", "wb") as f:
                f.write(base64.b64decode(qr_b64))
            print(f"[+] QR guardado en qr_code.png — escanea con WhatsApp")
            return True
    print(f"[!] QR no disponible: {json.dumps(result, indent=2)[:500]}")
    return False


def get_pairing_code(phone: str):
    print(f"[*] Solicitando código de apareamiento para {phone}...")
    result = request("POST", f"/instance/pairing/{INSTANCE}", {
        "number": phone,
    })
    code = result.get("code") or result.get("pairingCode")
    if code:
        print(f"[+] Código de apareamiento: {code}")
        print(f"    Abre WhatsApp → 3 puntos → Dispositivos vinculados → Vincular")
        return code
    print(f"[!] Error obteniendo código: {json.dumps(result, indent=2)[:500]}")
    return None


def show_status():
    print(f"\n{'='*50}")
    print(f"  EVOLUTION API STATUS — {INSTANCE}")
    print(f"{'='*50}")

    result = request("GET", f"/instance/connectionState/{INSTANCE}")
    state = result.get("state", {})
    if not state:
        state = result
    print(f"  Estado:        {state.get('state', 'DESCONOCIDO')}")
    print(f"  Instance:      {state.get('instance', INSTANCE)}")
    print(f"  Connected:     {state.get('connected', 'N/A')}")
    print(f"  Phone Linked:  {state.get('phone', {}).get('linked', 'N/A')}")

    print(f"\n  Endpoints disponibles:")
    print(f"    POST http://localhost:8080/message/sendText/{INSTANCE}")
    print(f"    POST http://localhost:8080/message/sendMedia/{INSTANCE}")
    print(f"    Webhook: POST http://localhost:8080/webhook/whatsapp-webhook")


def main():
    parser = argparse.ArgumentParser(description="Reconectar Evolution API a WhatsApp")
    parser.add_argument("--status", action="store_true", help="Ver estado")
    parser.add_argument("--qr", action="store_true", help="Obtener QR")
    parser.add_argument("--pairing", type=str, help="Código de apareamiento (número telefónico)")
    parser.add_argument("--create", action="store_true", help="Crear instancia")
    parser.add_argument("--auto", action="store_true", help="Auto: create → qr → pairing")
    parser.add_argument("--phone", type=str, default="5219999999999", help="Teléfono para pairing")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.create:
        create_instance()
        return

    if args.qr:
        create_instance()
        get_qr()
        return

    if args.pairing:
        create_instance()
        get_pairing_code(args.pairing)
        return

    if args.auto:
        print("\n[--- MODO AUTOMÁTICO ---]\n")
        create_instance()
        time.sleep(2)
        get_qr()
        time.sleep(1)
        if args.phone:
            get_pairing_code(args.phone)
        return

    show_status()
    print(f"\nUSO: python scripts/reconnect_evolution.py [--status|--qr|--pairing <tel>|--auto]")
    print(f"  --status        Mostrar estado")
    print(f"  --qr            Generar QR")
    print(f"  --pairing <tel> Generar código de apareamiento")
    print(f"  --auto          Todo automático")
    print(f"  --phone <tel>   Teléfono (default: 5219999999999)")


if __name__ == "__main__":
    main()
