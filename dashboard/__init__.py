"""
Paquete dashboard/ — generacion del dashboard estatico MOUNTS-Chile.

Descompone el antiguo generar_html.py (dios-archivo, refactor C2) en modulos
por responsabilidad. generar_html.py queda como orquestador delgado que importa
de aca y produce el mismo index.html / latest.html / map.html.

Submodulos:
  config    — constantes compartidas (paths, volcanes, paletas) + esc()
  charts    — graficos Plotly per-volcano + streamgraph
  status    — status board 7x4 + bulletin + diff vs ayer + helpers de formato
  map       — mapa Folium
  sections  — secciones HTML (volcan, alertas, multi, historico, upstream)
  template  — HTML base + CSS + ensamblado final
"""
