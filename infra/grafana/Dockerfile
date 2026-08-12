# Grafana con el aprovisionamiento horneado (WP-30b, decisión D8).
#
# Por qué imagen propia y no la de upstream con un volumen: aprovisionar
# fuentes de datos y paneles exige ficheros en disco, y el diseño de este
# WP renunció a EFS a propósito (Fargate + NFS para algo que sólo se lee
# al arrancar es coste y una pieza con estado que mantener). Horneando el
# JSON dentro, el despliegue es la única vía de cambiar un panel: lo que
# alguien edite en la UI se pierde en el siguiente rollout, que es
# exactamente lo que pide D8.
#
# ARM porque Grafana publica arm64 y en eu-south-2 Fargate ARM es ~20-25%
# más barato. Los servicios de la app siguen en x86 (sus imágenes se
# construyen --platform linux/amd64); migrarlas es otro asunto.
FROM grafana/grafana:11.6.0

# ``provisioning`` es lo que Grafana lee al arrancar. Los .yaml declaran
# fuentes y de dónde cargar paneles; los .json son los paneles.
COPY provisioning /etc/grafana/provisioning
COPY dashboards /var/lib/grafana/dashboards

# Sin registro de usuarios y sin acceso anónimo: el ALB publica esto en
# internet y lo único que hay delante es el login de Grafana.
ENV GF_USERS_ALLOW_SIGN_UP=false \
    GF_AUTH_ANONYMOUS_ENABLED=false \
    GF_ANALYTICS_REPORTING_ENABLED=false \
    GF_ANALYTICS_CHECK_FOR_UPDATES=false
