#-------------------------------------------------------------------------------
# $Id$
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
#-------------------------------------------------------------------------------
# Copyright (C) 2011 EOX IT Services GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell 
# copies of the Software, and to permit persons to whom the Software is 
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies of this Software or works derived from this Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#-------------------------------------------------------------------------------


import os
import logging
from itertools import chain
from uuid import uuid4
from datetime import datetime
import time
from os.path import splitext, basename

import numpy as np
from django.utils.datastructures import SortedDict
from django.contrib.gis.geos import Polygon

from eoxserver.core import Component, implements
from eoxserver.core.config import get_eoxserver_config
from eoxserver.contrib import mapserver as ms
from eoxserver.contrib import ogr, gdal, osr
from eoxserver.resources.coverages import crss
from eoxserver.services.result import result_set_from_raw_data, get_content_type
from eoxserver.services.exceptions import RenderException
from eoxserver.services.ows.wms.exceptions import InvalidCRS, InvalidFormat
from eoxserver.services.ows.wms.interfaces import WMSMapRendererInterface

#from wmm.grid import grid
from wmm.wrapper import main

logger = logging.getLogger(__name__)


class MapServerWMSBaseComponent(Component):
    """ Base class for various WMS render components using MapServer.
    """

    implements(WMSMapRendererInterface)

    def render(self, layers, bbox, crs, size, frmt, time, elevation, styles):
        if not time:
            raise RenderException("Missing mandatory 'time' parameter.")

        try:
            time = time.value
        except AttributeError:
            raise RenderException(
                "Parameter 'time' must be a slice and not a range."
            )

        llbbox = self.get_llbbox(bbox, crs)

        mapfile_path = get_eoxserver_config().get("wmm", "mapfile")
        map_ = ms.mapObj(mapfile_path) #TODO: path to map
        map_.setMetaData("ows_enable_request", "*")
        map_.setProjection("EPSG:4326")
        map_.imagecolor.setRGB(0, 0, 0)
        
        # set supported CRSs
        decoder = crss.CRSsConfigReader(get_eoxserver_config())
        crss_string = " ".join(
            map(lambda crs: "EPSG:%d" % crs, decoder.supported_crss_wms)
        )
        map_.setMetaData("ows_srs", crss_string)
        map_.setMetaData("wms_srs", crss_string)

        datasources = []
        datasets = []

        for layer_name in layers:
            layer = map_.getLayerByName(layer_name)
            if not layer:
                continue

            product = layer.metadata.get("wmm_product")

            filename = self.generate_filename("tif")
            ds = self.create_dataset(
                llbbox, time, elevation, size, product, filename
            )
            datasets.append(ds)

            if layer.type == ms.MS_LAYER_LINE:
                flavor = layer.metadata.get("wmm_flavor")
                contour_steps = self.get_contour_intervals(
                    flavor, llbbox, size
                )
                filename = self.generate_filename("shp")
                self.generate_contours(
                    ds, contour_steps, filename
                )
                
                layer.connectiontype = ms.MS_OGR
                layer.connection = filename
                layer.data, _ = splitext(basename(filename))

                datasources.append(filename)


        ms_request = ms.create_request((
            ("service", "WMS"),
            ("version", "1.3.0"),
            ("request", "GetMap"),
            ("layers", ",".join(layers)),
            ("bbox", "%f,%f,%f,%f" % (bbox[1], bbox[0], bbox[3], bbox[2])),
            ("crs", crs),
            ("width", str(size[0])),
            ("height", str(size[1])),
            ("styles", ",".join(styles)),
            ("format", frmt)
        ))

        raw_result = ms.dispatch(map_, ms_request)
        result = result_set_from_raw_data(raw_result)

        shp_drv = ogr.GetDriverByName("ESRI Shapefile")
        # cleanup datasources and datasets
        for filename in datasources:
            shp_drv.DeleteDataSource(filename)

        for ds in datasets:
            driver = ds.GetDriver()
            for filename in ds.GetFileList():
                os.remove(filename)


        return result, get_content_type(result)

    """
    def create_dataset(self, llbbox, time, elevation, size, product, out_file):
        ftime = to_year_fraction(time)

        if llbbox[0] < -180 or llbbox[1] < -90 or llbbox[2] > 180 or llbbox[3] > 90:
            raise RenderException("Out of valid range.", "bbox")

        resx = (llbbox[2] - llbbox[0]) / (size[0] - 1)
        resy = (llbbox[3] - llbbox[1]) / (size[1] - 1)

        logger.debug("Querying WMM grid for %s" % out_file)

        array = grid(
            llbbox[0], llbbox[1], elevation, ftime, 
            llbbox[2], llbbox[3], elevation, ftime,
            resx, resy, 1, 1, product, "/var/wmm/WMM.COF"
        )
        logger.debug("Finished querying WMM grid for %s" % out_file)

        array = np.flipud(array[0,:,:,0])

        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(out_file, size[0], size[1], 1, gdal.GDT_Float32)
        ds.GetRasterBand(1).WriteArray(array)

        ds.SetProjection(srs.ExportToWkt())
        ds.SetGeoTransform((llbbox[0], resx, 0, llbbox[3], 0, -resy))

        logger.debug("Saving %s" % out_file)
        return ds
    """

    def create_dataset(self, llbbox, time, elevation, size, product, out_file):
        if size[0] != size[1]:
            raise RenderException("Size needs to be quadratic.", "width")

        resx = (llbbox[2] - llbbox[0]) / size[0]
        resy = (llbbox[3] - llbbox[1]) / size[1]

        wmmbbox = (
            llbbox[1],# - resy,
            llbbox[0],# - resx, 
            llbbox[3],# + resy,
            llbbox[2],# + resx
        )

        return main(
            out_file, product, wmmbbox, size[0],# + 2, 
            elevation, to_year_fraction(time)
        )


    def generate_contours(self, ds, contour_steps, out_file):
        logger.debug("Generating contours for file %s" % ds.GetFileList()[0])
        driver = ogr.GetDriverByName('ESRI Shapefile')
        ogr_ds = driver.CreateDataSource(out_file)
        ogr_lyr = ogr_ds.CreateLayer('contour')
        field_defn = ogr.FieldDefn('ID', ogr.OFTInteger)
        ogr_lyr.CreateField(field_defn)
        field_defn = ogr.FieldDefn('elev', ogr.OFTReal)
        ogr_lyr.CreateField(field_defn)

        gdal.ContourGenerate(
            ds.GetRasterBand(1), contour_steps, 0, [], 0, 0, ogr_lyr, 0, 1
        )

        logger.debug("Finished generating contours for file %s" % ds.GetFileList()[0])
        return ogr_ds

    def generate_filename(self, ext):
        return "/tmp/%s.%s" % (uuid4().hex, ext)

    def get_llbbox(self, bbox, crs):
        srid = crss.parseEPSGCode(
            crs, (crss.fromShortCode, crss.fromURN, crss.fromURL)
        )

        if srid != 4326:
            
            poly = Polygon.from_bbox((bbox))
            poly.srid = 4326

            poly.transform(srid)
            return poly.extent

        return bbox


    def get_contour_intervals(self, flavor, llbbox, size):
        resolution = (llbbox[2] - llbbox[0]) / size[0]

        zoomlevel = 0
        iso_intervals = {
            "1": {
                0: 10,
                1: 10,
                2: 5,
                3: 5,
                4: 1,
                5: 1,
                6: 0.5,
                7: 0.5,
                8: 0.1
            },
            "2": {
                0: 5000,
                1: 5000,
                2: 2500,
                3: 1000,
                4: 1000,
                5: 1000,
                6: 500,
                7: 500,
                8: 100
            }
        }

        zoomresolution = [
            0.70312500,
            0.35156250,
            0.17578125,
            0.08789063,
            0.04394531,   
            0.02197266,
            0.01098633,
            0.00549316,
            0.00274658,
            0.00137329,
            0.00068665
        ]

        for i, res in enumerate(zoomresolution):
            if resolution < res:
                continue
            else:
                zoomlevel = i
                break

        print "Resolution: ", resolution, "Zoomlevel", zoomlevel

        return iso_intervals[flavor][zoomlevel]



    def check_parameters(self, map_, request_values):
        for key, value in request_values:
            if key.lower() == "format":
                if not map_.getOutputFormatByName(value):
                    raise InvalidFormat(value)
                break
        else:
            raise RenderException("Missing 'format' parameter")        

def to_year_fraction(v):
    def sinceEpoch(v): # returns seconds since epoch
        return time.mktime(v.timetuple())
    s = sinceEpoch

    year = v.year
    startOfThisYear = datetime(year=year, month=1, day=1)
    startOfNextYear = datetime(year=year+1, month=1, day=1)

    yearElapsed = s(v) - s(startOfThisYear)
    yearDuration = s(startOfNextYear) - s(startOfThisYear)
    fraction = yearElapsed / yearDuration

    return v.year + fraction
