# camera_catraca.py
# -----------------------------------------------------------------------------
# CÂMERA INTEGRADA (catraca virtual) do sistema unificado.
#
# Faz o que o antigo catraca.py fazia — detecta a CARTEIRINHA e a região da
# MATRÍCULA com YOLOv8, lê os dígitos com OCR (Tesseract) — mas em vez de
# publicar via MQTT para outro computador, registra a PASSAGEM
# DIRETAMENTE no mesmo banco do dashboard, chamando servico_acesso.
#
# Ou seja: um único computador com câmera lê a matrícula pela carteirinha e já
# contabiliza a entrada do aluno, mantendo o dashboard e todas as suas telas.
# -----------------------------------------------------------------------------

import os
import re
import sys
import time
import platform

import cv2
import pytesseract
from ultralytics import YOLO

from servico_acesso import processar_matricula

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# --- OCR / Tesseract -----------------------------------------------------------
# No Windows normalmente o executável fica neste caminho. Em Linux/macOS o
# Tesseract costuma estar no PATH, então só definimos o caminho se ele existir.
_TESS_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if platform.system() == "Windows" and os.path.exists(_TESS_WIN):
    pytesseract.pytesseract.tesseract_cmd = _TESS_WIN

CONFIG_TESS = r"--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789"

# --- Modelo YOLO ---------------------------------------------------------------
# Caminho relativo (funciona em qualquer máquina). Aceita variável de ambiente
# para sobrescrever, e cai no yolov8n.pt como último recurso.
def _resolver_modelo():
    candidatos = [
        os.getenv("MODELO_CATRACA"),
        os.path.join(BASE_DIR, "modelo_catraca.pt"),
        os.path.join(BASE_DIR, "runs", "detect", "train", "weights", "best.pt"),
        os.path.join(BASE_DIR, "yolov8n.pt"),
    ]
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError(
        "Modelo YOLO não encontrado. Esperado 'modelo_catraca.pt' na raiz do projeto."
    )


# Classes do modelo (ver config.yaml): 0 = carteirinha_celular | 1 = matricula
CLASSE_CARTEIRINHA = 0
CLASSE_MATRICULA = 1

PADRAO_MATRICULA = re.compile(r"\b20\d{9}\b")

# Cores (BGR) por status devolvido pelo servico_acesso
CORES = {
    "entrada": (0, 200, 0),
    "duplicado": (0, 165, 255),
    "fora_horario": (0, 165, 255),
    "refeicao_bloqueada": (0, 0, 255),
    "bloqueado": (0, 0, 255),
    "nao_cadastrado": (0, 0, 255),
    "erro": (0, 0, 255),
    "lendo": (255, 255, 255),
    "aguardando": (0, 255, 255),
}


def iniciar_camera(app, indice_camera=0, headless=False, tempo_de_trava=3.0):
    """Loop principal da câmera. Deve rodar na thread PRINCIPAL (janela OpenCV).

    app         -> instância Flask (para o contexto de banco)
    headless    -> True não abre janela (máquinas sem monitor); log no terminal
    tempo_trava -> segundos de bloqueio após uma leitura bem-sucedida
    """
    print("Carregando modelo YOLO da catraca...")
    model = YOLO(_resolver_modelo())

    cap = cv2.VideoCapture(indice_camera)
    if not cap.isOpened():
        print(f"❌ Não foi possível abrir a câmera (índice {indice_camera}).")
        return

    print("✅ Câmera integrada iniciada. Posicione a carteirinha. ('q' para sair)")

    frame_count = 0
    mensagem_tela = "POSICIONE A CARTEIRINHA"
    cor_mensagem = CORES["aguardando"]
    tempo_sucesso = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Falha ao ler frame da câmera.")
            break
        frame_count += 1

        resultados = model(frame, conf=0.6, verbose=False)
        caixas = resultados[0].boxes
        classes_detectadas = [int(c.cls[0]) for c in caixas]
        caixas_matricula = [c for c in caixas if int(c.cls[0]) == CLASSE_MATRICULA]

        # Só processa se o bloqueio pós-leitura já passou
        if time.time() - tempo_sucesso > tempo_de_trava:
            tem_carteirinha = CLASSE_CARTEIRINHA in classes_detectadas
            if tem_carteirinha and caixas_matricula:
                mensagem_tela = "LENDO MATRICULA..."
                cor_mensagem = CORES["lendo"]

                # OCR só de tempos em tempos (evita processar todo frame)
                if frame_count % 10 == 0:
                    x1, y1, x2, y2 = map(int, caixas_matricula[0].xyxy[0])
                    pad = 10
                    roi = frame[
                        max(0, y1 - pad):min(frame.shape[0], y2 + pad),
                        max(0, x1 - pad):min(frame.shape[1], x2 + pad),
                    ]

                    if roi.size > 0:
                        ampliado = cv2.resize(
                            roi, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC
                        )
                        gray = cv2.cvtColor(ampliado, cv2.COLOR_BGR2GRAY)
                        texto = pytesseract.image_to_string(gray, config=CONFIG_TESS)
                        achados = PADRAO_MATRICULA.findall(texto)

                        if achados:
                            matricula = achados[0]

                            # >>> UNIFICAÇÃO: registra direto no banco do dashboard
                            resultado = processar_matricula(app, matricula)
                            status = resultado["status"]

                            cor_mensagem = CORES.get(status, CORES["erro"])
                            if status == "entrada":
                                nome = (resultado["nome"] or "").split()[0]
                                mensagem_tela = f"LIBERADO: {nome} ({resultado['refeicao']})"
                            else:
                                mensagem_tela = resultado["mensagem"].upper()

                            print(f">>> [{status.upper()}] {resultado['mensagem']} ({matricula})")
                            tempo_sucesso = time.time()
            else:
                mensagem_tela = "AGUARDANDO CARTEIRINHA"
                cor_mensagem = CORES["aguardando"]

        if not headless:
            frame_anotado = resultados[0].plot()
            cv2.rectangle(frame_anotado, (10, 10), (640, 70), (0, 0, 0), -1)
            cv2.putText(
                frame_anotado, mensagem_tela, (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, cor_mensagem, 3,
            )
            cv2.imshow("Refeitorio - Catraca Integrada (Camera)", frame_anotado)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        else:
            # Sem janela: um pequeno respiro para não fritar a CPU
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    print("Câmera encerrada.")


if __name__ == "__main__":
    # Permite testar a câmera isoladamente: python camera_catraca.py
    from app import app
    headless = "--headless" in sys.argv
    iniciar_camera(app, headless=headless)
