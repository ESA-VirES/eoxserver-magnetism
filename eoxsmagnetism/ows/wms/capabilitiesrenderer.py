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

import logging

from eoxserver.core import Component, implements
from eoxserver.core.config import get_eoxserver_config
from eoxserver.contrib import mapserver as ms
from eoxserver.resources.coverages.crss import CRSsConfigReader
from eoxserver.services.result import (
    result_set_from_raw_data, get_content_type
)
from eoxserver.services.exceptions import RenderException
from eoxserver.services.ows.wms.exceptions import InvalidCRS, InvalidFormat
from eoxserver.services.ows.wms.interfaces import (
    WMSCapabilitiesRendererInterface
)

logger = logging.getLogger(__name__)


class MapServerCapabilitiesRenderer(Component):
    """ Base class for various WMS render components using MapServer.
    """

    implements(WMSCapabilitiesRendererInterface)


    def render(self):

        mapfile_path = get_eoxserver_config().get("wmm", "mapfile")
        map_ = ms.mapObj(mapfile_path) #TODO: path to map
        map_.setMetaData("ows_enable_request", "*")
        map_.setProjection("EPSG:4326")
        map_.imagecolor.setRGB(0, 0, 0)
        
        # set supported CRSs
        decoder = CRSsConfigReader(get_eoxserver_config())
        crss_string = " ".join(
            map(lambda crs: "EPSG:%d" % crs, decoder.supported_crss_wms)
        )
        map_.setMetaData("ows_srs", crss_string)
        map_.setMetaData("wms_srs", crss_string)

        ms_request = ms.create_request((
            ("service", "WMS"),
            ("version", "1.3.0"),
            ("request", "GetCapabilities"),
        ))

        raw_result = map_.dispatch(ms_request)
        result = result_set_from_raw_data(raw_result)
        return result, get_content_type(result)

