import mapscript as ms

m=ms.mapObj("test.map")

request = OWSRequest()
request.type = ms.MS_GET_REQUEST


#service=WMS&version=1.3.0&request=GetMap&layers=Declination&styles=&bbox=-90,-180,90,180&crs=EPSG:4326&format=image/png&width=256&height=256&time=2013-05-10&elevation=1
params = (
    ("service", "WMS"),
    ("version", "1.3.0"),
    ("request", "GetMap"),
    ("layers", "Declination"),
    ("bbox", "-90,-180,90,180"),
    ("crs", "EPSG:4326"),
    ("width", "256"),
    ("height", "256"),
    ("styles", ""),
    ("format", "image/png")
)

for k, v in params:
    request.setParameter(
        k, v
    )

m.OWSDispatch(request)