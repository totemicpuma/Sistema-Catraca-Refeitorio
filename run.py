# run.py
# -----------------------------------------------------------------------------
# PONTO DE ENTRADA ÚNICO do sistema unificado do refeitório.
#
# Um só comando sobe TUDO em uma máquina:
#   1) o servidor web Flask (dashboard completo) numa thread de fundo;
#   2) a CÂMERA integrada (catraca) que lê a carteirinha/matrícula e já
#      registra a passagem no mesmo banco — thread principal (janela);
#   3) opcionalmente, o receptor MQTT para catracas remotas extras.
#
# Uso:
#   python run.py                 -> dashboard + câmera integrada
#   python run.py --sem-camera    -> só o dashboard web
#   python run.py --headless      -> câmera sem janela (máquina sem monitor)
#   python run.py --mqtt          -> também escuta catracas remotas via MQTT
#   python run.py --porta 8080    -> muda a porta do dashboard (padrão 5000)
#   python run.py --camera 1      -> usa outra webcam (padrão índice 0)
# -----------------------------------------------------------------------------

import sys
import threading

from app import app


def _arg_valor(flag, padrao):
    """Lê o valor após uma flag na linha de comando (ex.: --porta 8080)."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return padrao


def iniciar_flask(porta):
    # use_reloader=False é obrigatório: o reloader do Flask reinicia o processo
    # e quebraria a thread da câmera. threaded=True atende câmera + web juntos.
    app.run(host="0.0.0.0", port=porta, debug=False,
            use_reloader=False, threaded=True)


def main():
    usar_camera = "--sem-camera" not in sys.argv
    headless = "--headless" in sys.argv
    usar_mqtt = "--mqtt" in sys.argv
    porta = int(_arg_valor("--porta", 5000))
    indice_camera = int(_arg_valor("--camera", 0))

    # 1) Dashboard web em thread de fundo (daemon: morre junto com o programa)
    threading.Thread(target=iniciar_flask, args=(porta,), daemon=True).start()
    print(f"Dashboard rodando em http://localhost:{porta}")

    # 2) Receptor MQTT opcional (catracas remotas), também em thread de fundo
    if usar_mqtt:
        from receptor_mqtt import iniciar_receptor_mqtt
        threading.Thread(
            target=iniciar_receptor_mqtt, args=(app,), daemon=True
        ).start()

    # 3) Câmera integrada NA THREAD PRINCIPAL (a janela do OpenCV exige isso)
    if usar_camera:
        from camera_catraca import iniciar_camera
        try:
            iniciar_camera(app, indice_camera=indice_camera, headless=headless)
        except FileNotFoundError as e:
            print(f"Aviso: {e}")
            print("O dashboard continua ativo. Encerre com Ctrl+C.")
            threading.Event().wait()
    else:
        # Sem câmera: mantém o processo vivo só com o dashboard
        print("Modo somente dashboard. Encerre com Ctrl+C.")
        threading.Event().wait()


if __name__ == "__main__":
    main()
