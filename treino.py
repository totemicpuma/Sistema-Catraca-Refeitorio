import os
from ultralytics import YOLO

# 1. Carrega o modelo YOLOv8 Nano (leve e super rápido)
print("Carregando o modelo YOLOv8n...")
model = YOLO('yolov8n.pt') 

# 2. Parâmetros de Treinamento (usando as técnicas de aumento do projeto do Naruto)
training_params = {
    'data': 'config.yaml',  # Nosso arquivo mapa
    'epochs': 50,           # Quantas vezes ele vai estudar as fotos (50 é um ótimo começo)
    'imgsz': 640,           # Tamanho da imagem que ele vai analisar
    'degrees': 10.0,        # Rotação (bom para celular inclinado)
    'translate': 0.1,       
    'scale': 0.5,           
    'fliplr': 0.5,          # Espelhar imagem horizontalmente
    'mosaic': 1.0,          
}

# 3. Inicia o treinamento!
print("Iniciando o treinamento da IA... Isso pode demorar alguns minutos!")
results = model.train(**training_params)

print("\n✅ Treinamento concluído com sucesso!")