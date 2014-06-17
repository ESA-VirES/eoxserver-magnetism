#!/bin/sh -e

# allow a custom EOxServer location to override the default one if needed
export EOX_ROOT=${1:-"/var/eoxserver"}

# Locate sudo (when available) for commands requiring the superuser.
# Allows setup of a custom autoconf instance located in the non-root user-space.
SUDO=`which sudo`

# Add CRS 900913 if not present
if ! grep -Fxq "<900913> +proj=tmerc +lat_0=0 +lon_0=21 +k=1 +x_0=21500000 +y_0=0 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs  <>" /usr/share/proj/epsg ; then
    $SUDO sh -c 'echo "# WGS 84 / Pseudo-Mercator" >> /usr/share/proj/epsg'
    $SUDO sh -c 'echo "<900913> +proj=tmerc +lat_0=0 +lon_0=21 +k=1 +x_0=21500000 +y_0=0 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs  <>" >> /usr/share/proj/epsg'
fi

cd /var/wmm

$SUDO python setup.py install

# EOxServer
cd "$EOX_ROOT/"
$SUDO python setup.py develop

cd /var/eoxsmagnetism

$SUDO python setup.py develop


# Configure EOxServer autotest instance
cd /var/eoxsmagnetism/instance

# Prepare DBs
python manage.py syncdb --noinput --traceback
python manage.py loaddata auth_data.json --traceback

# Create admin user
python manage.py shell 1>/dev/null 2>&1 <<EOF
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
if authenticate(username='admin', password='admin') is None:
    User.objects.create_user('admin','office@eox.at','admin')
EOF

# Collect static files
python manage.py collectstatic --noinput
