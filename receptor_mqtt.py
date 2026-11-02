# receptor_mqtt.py
# -----------------------------------------------------------------------------
# Receptor MQTT OPCIONAL — mantém a compatibilidade com o modelo de "2
# computadores": catracas REMOTAS rodando o antigo catraca.py continuam
# publicando a matrícula no broker, e este receptor registra a passagem
# no MESMO banco do dashboard (via servico_acesso).
#
# No sistema unificado a câmera local já registra direto, então isto é usado
# só se você tiver catracas extras espalhadas. Ative com:  python run.py --mqtt
# -----------------------------------------------------------------------------

import json

import paho.mqtt.client as mqtt

from servico_acesso import processar_matricula

BROKER = "broker.hivemq.com"
TOPICO = "isaac/catraca/leitura"
PORTA = 1883


def iniciar_receptor_mqtt(app, broker=BROKER, topico=TOPICO, porta=PORTA):
    """Escuta o broker e processa cada matrícula recebida. Bloqueante —
    normalmente chamado dentro de uma thread daemon a partir do run.py."""

    def ao_receber_mensagem(client, userdata, msg):
        try:
            dados = json.loads(msg.payload.decode("utf-8"))
            matricula = dados.get("matricula")
            print(f"\n📡 [MQTT] Recebido da catraca remota: {matricula}")
            resultado = processar_matricula(app, matricula)
            print(f"   -> [{resultado['status'].upper()}] {resultado['mensagem']}")
        except Exception as e:
            print(f"❌ [MQTT] Erro ao processar mensagem: {e}")

    print("Iniciando receptor MQTT (catracas remotas)...")
    client = mqtt.Client()
    client.on_message = ao_receber_mensagem
    client.connect(broker, porta, 60)
    client.subscribe(topico, qos=1)
    print(f"Escutando o tópico '{topico}'...")
    client.loop_forever()


if __name__ == "__main__":
    from app import app
    iniciar_receptor_mqtt(app)
