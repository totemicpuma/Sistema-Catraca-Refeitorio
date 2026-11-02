import os
import cv2

data_directory = 'dataset_carteirinha/0'

if not os.path.exists(data_directory):
    os.makedirs(data_directory)

camera_index = 0
video_cap = cv2.VideoCapture(camera_index)

print('\n--- Iniciando captura manual LIVRE ---')
print("Instruções:")
print("- Pressione 's' para salvar uma foto.")
print("- Pressione 'q' para PARAR as capturas e fechar o programa.\n")

counter = 0


while True:
    ret, frame = video_cap.read()
    
    if not ret:
        print("Erro ao ler a câmera.")
        break

    tela = frame.copy()
    
    cv2.putText(tela, f'Fotos salvas: {counter}', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(tela, 'Aperte "s" para foto | "q" para PARAR', (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
    
    cv2.imshow('Captura Manual - Carteirinha', tela)
    
    tecla = cv2.waitKey(1) & 0xFF
    
    # Botão de Salvar
    if tecla == ord('s'):
        caminho_arquivo = os.path.join(data_directory, f'excesso_{counter}.jpg')
        cv2.imwrite(caminho_arquivo, frame)
        print(f"✅ Foto {counter + 1} salva com sucesso!")
        counter += 1
        
    # BOTÃO DE PARAR
    elif tecla == ord('q'):
        print(f"\nCaptura finalizada pelo usuário!")
        print(f"Total de imagens capturadas: {counter}")
        break

video_cap.release()
cv2.destroyAllWindows()
print("Processo encerrado. Verifique a pasta 'dataset_carteirinha/0'.")