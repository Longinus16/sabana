import base64
from urllib.parse import quote as urlquote
from flask import Flask, send_from_directory
import dash
import dash_leaflet as dl
from dash import callback_context
from dash import dcc, html, Input, Output, State
import os
import re
import dash_leaflet.express as dlx
from datetime import datetime, timedelta
import io
import pandas as pd
import numpy as np
import colorsys
import warnings
import time
warnings.filterwarnings("ignore")

directorio_actual = os.getcwd()
nombre_directorio = "app_uploaded_files"

UPLOAD_DIRECTORY = os.path.join(directorio_actual, nombre_directorio)
if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)

def get_unique_color(index, total_files):
    hue = index / total_files
    rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.8)
    color = "#{:02x}{:02x}{:02x}".format(
        int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
    )
    return color

def dms_to_decimal(dms):
    if isinstance(dms, float):
        return dms
    else:
        match = re.search(r"(\d+)�(\d+)'([\d\.]+)\"([NSEW])", dms)
        if match:
            degrees, minutes, seconds, direction = match.groups()
            decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
            if direction in ['S', 'W']:
                decimal = -decimal
            return decimal
        else:
            return None


def prepare_df(path):
    columnas = ["Fecha", "Hora","Latitud","Longitud"]
    path = f'{path}'
    if "csv" in path:
        sabana = pd.read_csv(path)
    elif "xlsx" in path:
        sabana = pd.read_excel(path)
    else:
        return None
    for idx, column_name in enumerate(sabana):
        column = column_name.lower()
        if "fecha de la comunicación" == column:
            sabana['Fecha'] = sabana[column_name]
        if "fecha" == column:
            sabana['Fecha'] = sabana[column_name]
        if "hora de la comunicación" == column:
            sabana['Hora'] = sabana[column_name]
        if "hora" == column:
            sabana['Hora'] = sabana[column_name]
        if "latitud" == column:
            sabana['Latitud'] = sabana[column_name]
        if "longitud" == column:
            sabana['Longitud'] = sabana[column_name]
        if "LATITUD" == column:
            sabana['Latitud'] = sabana[column_name]
        if "LONGITUD" == column:
            sabana['Longitud'] = sabana[column_name]
        if "ubicacion geografica (latitud / longitud)" == column:
            sabana['Latitud'] = sabana.iloc[:,idx]
            sabana['Longitud'] = sabana.iloc[:,idx+1]
            sabana['Latitud'] = sabana['Latitud'].apply(dms_to_decimal)
            sabana['Longitud'] = sabana['Longitud'].apply(dms_to_decimal)
            
    formato = sabana.at[0, 'Fecha']
    if "-" in formato:
        formato = '%Y-%m-%d'
        
    if "/" in formato:
        formato = '%d/%m/%Y'
    sabana['Fecha'] = pd.to_datetime(sabana['Fecha'], format=formato, errors='coerce')
    sabana = sabana.drop_duplicates(subset=columnas)
    sabana = sabana.dropna(subset=["Latitud","Longitud"])
    sabana = sabana[sabana['Latitud'].astype(str).str.contains('\.') & sabana['Longitud'].astype(str).str.contains('\.')]
    sabana["Latitud"] = sabana["Latitud"].astype(float)
    sabana["Longitud"] = sabana["Longitud"].astype(float)
    return sabana[columnas]

server = Flask(__name__)
app = dash.Dash(server=server)

@server.route("/download/<path:path>")
def download(path):
    """Serve a file from the upload directory."""
    return send_from_directory(UPLOAD_DIRECTORY, path, as_attachment=True)

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),  
    dcc.Upload(
        id="upload-data",
        children=html.Div(["Seleccionar una sabana telefonica"]),
        style={
            "width": "100%",
            "height": "60px",
            "lineHeight": "60px",
            "borderWidth": "1px",
            "borderStyle": "dashed",
            "borderRadius": "5px",
            "textAlign": "center",
            "margin": "10px",
        },
        multiple=True,
    ),
    html.Div(
        id='file-list-container',
        children=[
            html.Ul(id="file-list", style={"list-style-type": "none", "padding": 0}),
        ],
        style={"max-width": "200px", "max-height": "200px", "overflow": "auto", "float": "right", "margin-right": "10px"}
    ),


    html.Button('Borrar Archivos', id='btn-limpiar', style={"margin": "10px",
                           "background-color": "#f44336",  
                           "color": "white",              
                           "font-size": "16px",          
                           "padding": "10px 24px"}),
    dcc.DatePickerSingle(
        id='date-picker',
        display_format='YYYY-MM-DD',
        with_portal=True,
        style={
            'display': 'inline-block',
            'margin-right': '10px',
            'color': 'black',  # letras negras
            'border-radius': '50px',  # borde circular
            'padding': '5px 10px',  # espacio interno
        }
    ),
    html.Button('Identificar coincidencias', 
                    id='btn-coincidencias', 
                    style={"margin": "10px",
                           "background-color": "#4CAF50",  # Verde
                           "color": "white",              # Texto blanco
                           "font-size": "16px",           # Tamaño de fuente
                           "padding": "10px 24px"}),
    html.Button('Actualizar', 
                    id='btn-refresh', 
                    style={"margin": "10px",
                           "background-color": "#3d85c6",  # Verde
                           "color": "white",              # Texto blanco
                           "font-size": "16px",           # Tamaño de fuente
                           "padding": "10px 24px"}),
    dcc.Slider(
        id='hour-slider',
        min=0,
        max=24,
        step=1,
        marks={i: f'{i}:00' for i in range(0, 25)},
        value=15
    ),
    dl.Map(id='map', style={'width': '100%', 'height': '70vh'}),
])


def save_file(name, content):
    data = content.encode("utf8").split(b";base64,")[1]
    with open(os.path.join(UPLOAD_DIRECTORY, name), "wb") as fp:
        fp.write(base64.decodebytes(data))


def uploaded_files():
    files = []
    for filename in os.listdir(UPLOAD_DIRECTORY):
        path = os.path.join(UPLOAD_DIRECTORY, filename)
        if os.path.isfile(path):
            files.append(filename)
    return files


def file_download_link(filename):
    location = "/download/{}".format(urlquote(filename))
    return html.A(filename, href=location)

@app.callback(
    Output("file-list", "children"),
    [Input("upload-data", "filename"),
     Input('btn-limpiar', 'n_clicks'),
     Input("upload-data", "contents")],
    [State('file-list', 'children')]
)
def update_output(uploaded_filenames, n_clicks, uploaded_file_contents, current_children):
    if n_clicks is not None:
        return [html.Li("Archivo borrado")]

    if uploaded_filenames is not None and uploaded_file_contents is not None:
        for name, data in zip(uploaded_filenames, uploaded_file_contents):
            save_file(name, data)
            
    files = uploaded_files()
    if len(files) == 0:
        return [html.Li("Sin archivo!")]
    else:
        return [html.Li(file_download_link(filename)) for filename in files]
def validate_ddays(disabled_days, dates_disabled):
    disabled_days_values = list(filter(lambda day: day not in dates_disabled, disabled_days))
    return disabled_days_values
def truncate_float(x):
    s = str(x)
    decimal_index = s.find('.')
    if decimal_index != -1:
        s = s[:decimal_index + 6]
    return float(s)

def encontrar_coincidencias(df, fecha_elegida,selected_hour):
    print("dia",fecha_elegida, "hora: ", selected_hour)
    df = df[df['Fecha'] == fecha_elegida]
    df = df[df['Hora'].str[:2].astype(int) < selected_hour]
    df['Latitud'] = df['Latitud'].apply(truncate_float).astype(float)
    df['Longitud'] = df['Longitud'].apply(truncate_float).astype(float)
    df["HoraInt"] = df['Hora'].str[:2].astype(int)
    #duplicated = df[df.duplicated(subset=['Latitud', 'Longitud', 'file'], keep="first")] #primero eliminamos los duplicados donde para que sean direcciones unicas
    duplicated = df.drop_duplicates(subset=['Latitud', 'Longitud', 'file'])
    duplicated_unique = df[df.duplicated(subset=['Latitud', 'Longitud'], keep=False) 
                           & ~df.duplicated(subset=['Latitud', 'Longitud', 'file'], keep=False)]
    duplicated = duplicated_unique.drop_duplicates(subset=['Latitud', 'Longitud'], keep="first")
    duplicated.to_csv("duplicados.csv",index=False)
    circles = []
    print(duplicated)
    if(not duplicated.empty):
        for index, row in duplicated.iterrows(): 
            lat_mean = row['Latitud']
            lon_mean = row['Longitud']
            circle = dl.Circle(center=[lat_mean, lon_mean], radius=1900)
            circles.append(circle)
        return circles  
    else:
        return []

@app.callback(
    [Output('map', 'children'),
     Output('date-picker', 'date'),
     Output('date-picker', 'disabled_days')],
    [Input('upload-data', 'contents'),
     Input('btn-limpiar', 'n_clicks'),
     Input('btn-refresh', 'n_clicks'),
     Input('btn-coincidencias', 'n_clicks')
     ],
    [Input('upload-data', 'filename'),
     Input('date-picker', 'date'),
     Input('hour-slider', 'value')]  
)
def update_output(archivos, n_clicks, nclicksr,coincidencias, nombres_archivos, fecha_elegida, selected_hour):
    map_children = []
    disabled_days = []
    files_guardados = os.listdir(UPLOAD_DIRECTORY)
    cantidad = len(files_guardados)
    if n_clicks is not None:
        for archivo in files_guardados:
            ruta_completa = os.path.join(UPLOAD_DIRECTORY, archivo)
            os.remove(ruta_completa)
        return [html.Div(f'Actualice la pagina para subir un archivo nuevamente'), None, []]
    if archivos is not None:
        time.sleep(1)
        files_guardados = os.listdir(UPLOAD_DIRECTORY)
        cantidad = len(files_guardados)+1
        print(cantidad)
    if (nclicksr is not None and len(files_guardados) == 0):
        return [html.Div(f'SUBA UN ARCHIVO'), None, []]    
    if cantidad > 0:
        revisado = True
        circles = []
        markers = []
        fechas_deshabilitadas = []
        fechas_permitidas_dt = []
        polyline_decorator = []
        for idx, name in enumerate(reversed(files_guardados)):
            df = prepare_df(os.path.join(UPLOAD_DIRECTORY, name))
            fechas_permitidas = [str(date) for date in pd.to_datetime(df['Fecha']).dt.date.unique()]
            fechas_permitidas_dt.extend(fechas_permitidas)
        for idx, name in enumerate(reversed(files_guardados)):
                print(name)
                dfs2 = []
                df = prepare_df(os.path.join(UPLOAD_DIRECTORY, name))
                df["file"] = name.split(".")[0]
                first_date = df['Fecha'].min()
                years_range = range(datetime.now().year - 2, datetime.now().year + 1)
                disabled_days = [date.strftime('%Y-%m-%d') for year in years_range for date in (datetime(year, 1, 1) + timedelta(n) for n in range(365)) if date.strftime('%Y-%m-%d') not in fechas_permitidas_dt]
                fechas_deshabilitadas.extend(disabled_days)
                if fecha_elegida is None:
                    fecha_elegida = first_date
                else:
                    fecha_elegida
                if(coincidencias is not None and revisado == True):
                    for name2 in reversed(files_guardados):
                        try:
                            df2 = prepare_df(os.path.join(UPLOAD_DIRECTORY, name2))
                            name2 = name2.split(".")[0]
                            df2["file"] = name2
                            dfs2.append(df2)
                            print("archivo: ",name2," con la cantidad de: ",len(df2))
                        except Exception as e:
                            print(f"Error al procesar el archivo {name}: {e}")
                    df_general = pd.concat(dfs2, ignore_index=True)
                    circles = encontrar_coincidencias(df_general, fecha_elegida,selected_hour)
                    revisado = False
                markers_part, polyline_decorator_part = create_markers(df, idx,fecha_elegida,selected_hour,name)
                markers += markers_part
                polyline_decorator += polyline_decorator_part
                
                if df.empty:
                    mensaje = html.Div("No hay datos disponibles para la fecha seleccionada.", style={'color': 'red'})
                    return [dl.Map(id='map', style={'width': '100%', 'height': '70vh'}), fecha_elegida, disabled_days]
                else:
                    map_children.append(
                        dl.Map(
                            [
                                dl.TileLayer(url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
                                *markers,
                                dl.FullScreenControl(),
                                polyline_decorator,
                                *circles
                            ],
                            center=(df['Latitud'][0], df['Longitud'][0]),
                            zoom=10,
                            id='map',
                            style={'width': '100%', 'height': '70vh','position': 'absolute', 'zIndex': 1}
                        )
                    )
            
        return [map_children, fecha_elegida, fechas_deshabilitadas]
    else:
        return [dl.Map(id='map', style={'width': '100%', 'height': '80vh','position': 'absolute', 'zIndex': 1}), None, []]

def create_markers(df, color_index,fecha_elegida,selected_hour,name):
    markers = []
    color_mapping = {
        0: "naranja",
        1: "rojo",
        2: "azul",
        3: "verde",
        4: "amarillo",
        5: "maps",
        6: "azules",
    }
    df = df[df['Fecha'] == fecha_elegida]
    df['Hora'] = df['Hora'].astype(str)  
    df = df[df['Hora'].str[:2].astype(int) < selected_hour]
    df['Cantidad'] = df.groupby(['Latitud', 'Longitud',"file"]).transform('count')['Fecha']
    df['Cantidad'] = df['Cantidad'].astype(int)
    df = df.drop_duplicates(subset=["Latitud","Longitud","file"])
    polyline_coordinates = [[row['Latitud'], row['Longitud']] for index, row in df.iterrows()]
    polyline = dl.Polyline(positions=polyline_coordinates,color="#ff7800")
    patterns = [dict(offset='0', repeat='10',dash=dict(pixelSize=1))]
    polyline_decorator = dl.PolylineDecorator(children=polyline, patterns=patterns)
    name = name.split(".")[0]
    for index, row in enumerate(df.iterrows()):
        row = row[1]
        color = color_mapping[color_index]  
        marker = dl.Marker(
            position=[row['Latitud'], row['Longitud']],
            icon = {
                "iconUrl": f'https://facebook.rimgsa.com/marcador{color}.png',
                "iconSize": [30, 40],       # Tamaño del icono
                "shadowSize": [50, 64],     # Tamaño de la sombra
                "iconAnchor": [12, 40],     # Punto del icono que corresponderá a la ubicación del marcador
                "shadowAnchor": [4, 32],    # Lo mismo para la sombra
                "popupAnchor": [-3, -38]    # Punto desde el cual se debe abrir el popup en relación con iconAnchor
            },
            children=[
                dl.Tooltip(html.Div([
                    html.Strong("Numero:"),
                    html.Br(),
                    f"{row['file']}",
                    html.Br(),
                    html.Strong("Fecha:"),
                    html.Br(),
                    f"{row['Fecha']}",
                    html.Br(),
                    html.Strong("Hora:"),
                    html.Br(),
                    f"{row['Hora']}",
                    html.Br(),
                    html.Strong("Cantidad de llamadas aquí:"),
                    html.Br(),
                    f"{row['Cantidad']}"
                ])),
            ]
        )
        markers.append(marker)
    return markers,polyline_decorator

if __name__ == '__main__':
    app.run_server(debug=True)