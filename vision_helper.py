from ultralytics import YOLO
import folium
import base64
import os
import pandas as pd
import numpy as np
from tqdm import tqdm
from geopy.distance import distance
import concurrent.futures
import requests
from PIL import Image
from io import BytesIO
import io
from google.cloud import vision
from google.oauth2 import service_account
import json
import google.genai
from geopy.point import Point
import re
from dotenv import load_dotenv

load_dotenv()

class Basuras():
    __API_KEY = os.getenv("API_KEY_STREET_VIEW")
    __BASE_LOCATION = []
    __BASE_COORD= None
    __CAPTURE_DISTANCE = None
    __STEP = None
    __RESULTS_FOLDER = None
    _LOCATION_NAME = None


    def buscar_basuras_en_zona(self, latitud, longitud, distancia, step):
        self.establecer_variables(latitud, longitud, distancia, step)
        df = self.start_data_collection()
        
        return df

    def establecer_variables(self, latitud, longitud, distancia, step):
        self.__BASE_LOCATION = [latitud, longitud]
        self.__BASE_COORD= Point(self.__BASE_LOCATION[0], self.__BASE_LOCATION[1])
        self.__CAPTURE_DISTANCE = [distancia, distancia]
        self.__STEP = step
        self._LOCATION_NAME = f"LT{latitud.replace('.', '_')}LG{longitud.replace('.', '_')}"
        self.__RESULTS_FOLDER = "./" + self._LOCATION_NAME + "_T" + pd.Timestamp.now().strftime("%Y%m%d_%H%M%S%f")

    def get_images_by_coord(self, location, folder):
        """Obtiene imágenes de Google Street View para una ubicación y las guarda como panorama."""
        size = "600x300"
        fov = 120
        pitch = 0
        headings = [0, 90, 180, 270]

        images = []
        all_success = True

        for heading in headings:
            url = f"https://maps.googleapis.com/maps/api/streetview?size={size}&location={location}&heading={heading}&fov={fov}&pitch={pitch}&key={self.__API_KEY}"
            response = requests.get(url)
            if response.status_code == 200:
                try:
                    img = Image.open(BytesIO(response.content))
                    images.append(img)
                except Exception as e:
                    print(f"Error al procesar la imagen de {heading}: {e}")
                    all_success = False
            else:
                print(f"Error al obtener las imágenes para la coordenada {heading}: {response.status_code}")
                all_success = False

        if all_success and images:
            width, height = images[0].size
            total_width = width * len(images)
            panorama = Image.new('RGB', (total_width, height))

            for i, img in enumerate(images):
                panorama.paste(img, (i * width, 0))

            time_stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S%f")
            location_name = "LT"+location.replace(".", "_").replace(",","LG")
            image_path = os.path.join(folder, f"{location_name}.jpg")

            try:
                panorama.save(image_path)
                print(f"Panorama guardado en: {image_path}")

                return image_path
            except Exception as e:
                print(f"Error al guardar el panorama: {e}")
                return None
        else:
            print(f"No se pudieron obtener imágenes válidas para {location}")
            return None
    def capture_image_and_create_row(self, x, y, coord, folder):
        """Captura una imagen y crea una fila para el DataFrame."""
        new_coord = distance(meters=x).destination(coord, bearing=0)
        new_coord = distance(meters=y).destination(new_coord, bearing=90)

        string_coord = "{:06f}".format(new_coord.latitude), "{:06f}".format(new_coord.longitude)
        string_coord = f"{string_coord[0]},{string_coord[1]}"

        image_path = self.get_images_by_coord(string_coord, folder)
        if image_path:
            img = Image.open(image_path)
            vision_yolo = VisionYolo()
            label = vision_yolo.get_yolo_label(img)
            description = VisionGoogle().get_gemini_description(img)
            return [new_coord.latitude, new_coord.longitude, image_path, label, description]
        else:
            return [new_coord.latitude, new_coord.longitude, "ERROR", "ERROR"]

    def start_data_collection(self):
        print("Iniciando proceso de captura de datos")
        print("Por favor espere...")

        # Verificar si la carpeta RESULTS_FOLDER existe y crearla si no
        if not os.path.exists(self.__RESULTS_FOLDER):
            os.makedirs(self.__RESULTS_FOLDER)
            print(f"Carpeta {self.__RESULTS_FOLDER} creada.")
        else:
            print(f"Carpeta {self.__RESULTS_FOLDER} ya existe.")

        total = (self.__CAPTURE_DISTANCE[0] * self.__CAPTURE_DISTANCE[1]) / (self.__STEP ** 2)
        pbar = tqdm(total=total, dynamic_ncols=True, position=0, leave=True,
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{rate_fmt}] {postfix}", colour='cyan')

        df = pd.DataFrame(columns=["Latitude", "Longitude", "Image", "Label", "Description"])
        rows = []

        x_origin = -1 * (self.__CAPTURE_DISTANCE[0] / 2)
        x_end = self.__CAPTURE_DISTANCE[0] / 2
        y_origin = -1 * (self.__CAPTURE_DISTANCE[1] / 2)
        y_end = self.__CAPTURE_DISTANCE[1] / 2

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for x in np.arange(x_origin, x_end, self.__STEP):
                for y in np.arange(y_origin, y_end, self.__STEP):
                    futures.append(executor.submit(self.capture_image_and_create_row, x, y, self.__BASE_COORD, self.__RESULTS_FOLDER))

            for future in concurrent.futures.as_completed(futures):
                rows.append(future.result())
                pbar.update(1)

        pbar.close()

        for row in rows:
            df.loc[len(df)] = row

        print("Proceso finalizado")
        print("Se han tomado", len(df), "capturas")
        df.to_csv(f"{self.__RESULTS_FOLDER}/{self._LOCATION_NAME}.csv")

        return df



class VisionGoogle():
    __API_KEY = os.getenv("API_KEY_VISION_GOOGLE")

    __description_prompt=  """
    Eres un experto en análisis visual de calles para apoyar la gestión eficiente del aseo urbano. Recibirás una imagen compuesta por cuatro tomas distintas de una misma calle. Realiza el siguiente procedimiento de análisis:

    # Paso 1: Validación inicial de la imagen
        Confirma primero si la imagen cumple estos requisitos:
        - Muestra claramente cuatro tomas de una misma calle.
        - Corresponde efectivamente a un espacio público exterior.

        Si la imagen no cumple con alguno de los criterios establecidos (por ejemplo: no es visible, está dañada, muestra el interior de un establecimiento comercial, o fue tomada por error), indica en la justificación que la imagen no corresponde y explica el motivo específico.
        Por ejemplo:
        "No se puede realizar el análisis: la imagen no corresponde a una calle con 4 tomas del espacio público, sino al interior de un establecimiento comercial." o "No se puede realizar el análisis: La imagen no está disponible." (O bien, proporciona una justificación basada en el problema detectado).

    # Paso 2: Análisis específico (si la imagen es válida)
        Responde claramente estas preguntas:
        1. ¿Qué tan limpia o sucia se ve la calle en general?
            Evalúa en una escala del 1 al 10 (10 = muy limpia, 1 = extremadamente sucia).
        2. ¿Se observan acumulaciones evidentes de basura en la imagen?
            Responde: Sí / No. Si la respuesta es Sí, indica brevemente la intensidad: (leve, moderada, alta). Si es No, clasifica la intensidad como (No Aplica)
        3. ¿La recolección de residuos parece urgente en esta calle?
            Responde con: No urgente / Moderadamente urgente / Urgente
        4. ¿Se observan papeleras o contenedores de basura en la calle?
            Responde con: Sí / No
        5. Justificación de la Evaluación. Indica las razones principales de tu evaluación

    Responde en el siguiente formato JSON EXACTAMENTE:
    {
        "es_imagen_valida": <bool>,
        "limpieza_general": <número entero de 1 a 10 o null>,
        "acumulacion_basura": <"Sí" o "No" o null>,
        "intensidad_basura": <"Leve", "Moderada", "Alta", "No Aplica" o null>,
        "recoleccion_urgente": <"No urgente", "Moderadamente Urgente", "Urgente" o null>,
        "papeleras_presentes": <"Sí" o "No" o null>,
        "justificacion": <cadena de texto con justificación>
    }
    No añadas ningún texto adicional OBLIGATORIO: NO USAR formato markdown en la salida.
    Responde siempre en idioma: "Spanish"
    """
    def get_image_from_location(self, location: str):
        """Obtiene imágenes de Google Street View y las organiza correctamente con padding."""

        size = "600x300"
        fov = 120
        pitch = 0
        headings = [0, 90, 180, 270]

        images = []
        try:
            for heading in headings:
                url = f"https://maps.googleapis.com/maps/api/streetview?size={size}&location={location}&heading={heading}&fov={fov}&pitch={pitch}&key={self.__API_KEY}"
                response = requests.get(url)
                if response.status_code == 200:
                    try:
                        img = Image.open(BytesIO(response.content))
                        images.append(img)
                    except Exception as e:
                        print(f"Error al procesar la imagen de {heading}: {e}")
                        return None
                else:
                    print(f"Error al obtener la imagen para {heading}: {response.status_code}")
                    return None
        except:
            return None

        if len(images) != 4:
            print(f"No se pudieron obtener todas las imágenes para {location}")
            return None

        # Crear un lienzo en blanco de 1200x600
        nuevo_ancho = 1200
        nuevo_alto = 600
        nueva_imagen = Image.new('RGB', (nuevo_ancho, nuevo_alto))

        # Colocar las imágenes en la posición correcta
        nueva_imagen.paste(images[0], (0, 0))     # Parte 1 - Arriba Izquierda
        nueva_imagen.paste(images[1], (600, 0))   # Parte 2 - Arriba Derecha
        nueva_imagen.paste(images[2], (0, 300))   # Parte 3 - Abajo Izquierda
        nueva_imagen.paste(images[3], (600, 300)) # Parte 4 - Abajo Derecha

        # Redimensionar la imagen a 600x300
        img_final = nueva_imagen.resize((600, 300), Image.ANTIALIAS)

        # Agregar padding para convertirla en 600x600
        img_con_padding = Image.new("RGB", (600, 600), (0, 0, 0))  # Fondo negro
        img_con_padding.paste(img_final, (0, 150))  # Centrar verticalmente

        return img_con_padding


    def get_gemini_description(self, img):
        """Obtiene una descripción de una imagen usando la API de Cloud Vision."""
        try:
            client = google.genai.Client(api_key=self.__API_KEY)
            model = client.models  # Accedemos al objeto models.

            response_gemini = model.generate_content(
                model='gemini-2.0-flash',
                contents=[
                    self.__description_prompt,
                    img
                ]
            )

            description = response_gemini.text.strip()
            description = description.replace('```json','').replace('```','')
            description = json.loads(description)
            return description
        except Exception as e:
            print(f"Error al obtener la descripción: {e}")
            return None

class VisionYolo():
    __model_path = "best.pt"
    def get_yolo_label(self, img)-> str:
        """Obtiene la etiqueta de clasificación de una imagen."""
        model = YOLO(self.__model_path)  # Reemplaza con la ruta a tu modelo
        results = model(img)
        etiqueta = results[0].names[results[0].probs.top1]
        return etiqueta