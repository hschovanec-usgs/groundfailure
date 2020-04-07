# stdlib imports

import os
import numpy as np
import urllib
import json
from datetime import timedelta
import collections
import matplotlib.pyplot as plt
import matplotlib.patches as patches
# import numpy as np
import sqlite3 as lite
import pandas as pd

# local imports
from mapio.shake import getHeaderData
from libcomcat.search import get_event_by_id, search
from mapio.basemapcity import BasemapCities
from mapio.multihaz import MultiHazardGrid


# Don't delete this, it's needed in an eval function
import matplotlib.cm as cm  # DO NOT DELETE
# DO NOT DELETE ABOVE LINE


def is_grid_point_source(grid):
    """Was the shakemap grid constructed with a point source?

    This makes use of the 'urat' layer, which is the ratio of the predicted
    ground motion standard deviation to the GMPE standard deviation. The only
    reason this could ever be greater than 1.0 is if the uncertainty of the
    prediction is inflated due to the point source approxmiation; further,
    if a point source was used, there will always be some
    locations with 'urat' > 1.0.

    Args:
        grid (ShakeGrid): A ShakeGrid object from MapIO.

    Returns:
        bool: True if point rupture.
    """
    data = grid.getData()
    urat = data['urat'].getData()
    max_urat = np.max(urat)
    if max_urat > (1 + np.finfo(float).eps):
        return True
    else:
        return False


def get_event_comcat(shakefile, timewindow=60, degwindow=0.3, magwindow=0.2):
    """
    Find an event in comcat, searching first by event id and if that
    fails searching by magnitude, time, and location.

    Args:
        shakefile (str): path to shakemap .xml file of event to find
        timewindow (float): width of time window to search around time defined
            in shakefile (in seconds)
        degwindow (float): width of area to search around location specified in
            shakefile (in degrees).
        magwindow (float): width of magnitude window to search around the
            magnitude specified in shakefile.

    Returns:
        None if event not found, else tuple (info, detail, shakemap) where,
            * info: json formatted dictionary of info.json for the event
            * detail: event detail from comcat
            * shakemap: shakemap of event found (from comcat)

    """
    header_dicts = getHeaderData(shakefile)
    grid_dict = header_dicts[0]
    event_dict = header_dicts[1]
    version = grid_dict['shakemap_version']
    try:
        eid = event_dict['event_id']
        net = 'us'
        if 'event_network' in event_dict:
            net = event_dict['event_network']
        if not eid.startswith(net):
            eid = net + eid
        detail = get_event_by_id(eid, includesuperseded=True)
    except Exception as e:
        lat = event_dict['lat']
        lon = event_dict['lon']
        mag = event_dict['magnitude']
        time = event_dict['event_timestamp']
        starttime = time - timedelta(seconds=timewindow)
        endtime = time + timedelta(seconds=timewindow)
        minlat = lat - degwindow
        minlon = lon - degwindow
        maxlat = lat + degwindow
        maxlon = lon + degwindow
        minmag = max(0, mag - magwindow)
        maxmag = min(10, mag + magwindow)
        events = search(starttime=starttime,
                        endtime=endtime,
                        minmagnitude=minmag,
                        maxmagnitude=maxmag,
                        minlatitude=minlat,
                        minlongitude=minlon,
                        maxlatitude=maxlat,
                        maxlongitude=maxlon)
        if not len(events):
            return None
        detail = events[0].getDetailEvent()
    allversions = detail.getProducts('shakemap', version='all')
    # Find the right version
    vers = [allv.version for allv in allversions]
    idx = np.where(np.array(vers) == version)[0][0]
    shakemap = allversions[idx]
    infobytes, url = shakemap.getContentBytes('info.json')
    info = json.loads(infobytes.decode('utf-8'))
    return info, detail, shakemap


def parseMapConfig(config, fileext=None):
    """
    Parse config for mapping options.

    Args:
        config (ConfigObj): ConfigObj object.
        fileext (str): File extension to add to relative filepaths, will be
            prepended to any file paths in config.

    Returns:
        dict: Dictionary of map options pulled from config file.
    """
    topofile = None
    roadfolder = None
    cityfile = None
    roadcolor = '6E6E6E'
    countrycolor = '177F10'
    watercolor = 'B8EEFF'
    ALPHA = 0.7
    oceanfile = None
    # oceanref = None
    # roadref = None
    # cityref = None

    if fileext is None:
        fileext = '.'
    if 'dem' in config:
        topofile = os.path.join(fileext, config['dem']['file'])
        if os.path.exists(topofile) is False:
            print('DEM not valid - hillshade will not be possible\n')
    if 'ocean' in config:
        oceanfile = os.path.join(fileext, config['ocean']['file'])
        # try:
        #     oceanref = config['ocean']['shortref']
        # except:
        #     oceanref = 'unknown'
    if 'roads' in config:
        roadfolder = os.path.join(fileext, config['roads']['file'])
        if os.path.exists(roadfolder) is False:
            print('roadfolder not valid - roads will not be displayed\n')
            roadfolder = None
        # try:
        #     roadref = config['roads']['shortref']
        # except:
        #     roadref = 'unknown'
    if 'cities' in config:
        cityfile = os.path.join(fileext, config['cities']['file'])
        # try:
        #     cityref = config['cities']['shortref']
        # except:
        #     cityref = 'unknown'
        if os.path.exists(cityfile):
            try:
                BasemapCities.loadFromGeoNames(cityfile=cityfile)
            except Exception as e:
                print(e)
                print('cities file not valid - cities will not be displayed\n')
                cityfile = None
        else:
            print('cities file not valid - cities will not be displayed\n')
            cityfile = None
    if 'roadcolor' in config['colors']:
        roadcolor = config['colors']['roadcolor']
    if 'countrycolor' in config['colors']:
        countrycolor = config['colors']['countrycolor']
    if 'watercolor' in config['colors']:
        watercolor = config['colors']['watercolor']
    if 'alpha' in config['colors']:
        ALPHA = float(config['colors']['alpha'])

    countrycolor = '#'+countrycolor
    watercolor = '#'+watercolor
    roadcolor = '#'+roadcolor

    mapin = {'topofile': topofile, 'roadfolder': roadfolder,
             'cityfile': cityfile, 'roadcolor': roadcolor,
             'countrycolor': countrycolor, 'watercolor': watercolor,
             'ALPHA': ALPHA, 'oceanfile': oceanfile}
    # 'roadref': roadref, 'cityref': cityref, 'oceanref': oceanref

    return mapin


def parseConfigLayers(maplayers, config, keys=None):
    """
    Parse things that need to coodinate with each layer (like lims, logscale,
    colormaps etc.) from config file, in right order, where the order is from
    maplayers.

    Args:
        maplayers (dict): Dictionary containing model output.
        config (ConfigObj): Config object describing options for specific
            model.
        keys (list): List of keys of maplayers to process, e.g. ``['model']``.

    Returns:
        tuple: (plotorder, logscale, lims, colormaps, maskthreshes) where:
            * plotorder: maplayers keys in order of plotting.
            * logscale: list of logscale options from config corresponding to
              keys in plotorder (same order).
            * lims: list of colorbar limits from config corresponding to keys
              in plotorder (same order).
            * colormaps: list of colormaps from config corresponding to keys
              in plotorder (same order),
            * maskthreshes: list of mask thresholds from config corresponding
              to keys in plotorder (same order).

    """
    # TODO:
    #    - Add ability to interpret custom color maps.

    # get all key names, create a plotorder list in case maplayers is not an
    # ordered dict, making sure that anything called 'model' is first
    if keys is None:
        keys = list(maplayers.keys())
    plotorder = []

    configkeys = list(config.keys())

    try:
        limits = config[configkeys[0]]['display_options']['lims']
        lims = []
    except:
        lims = None
        limits = None

    try:
        colors = config[configkeys[0]]['display_options']['colors']
        colormaps = []
    except:
        colormaps = None
        colors = None

    try:
        logs = config[configkeys[0]]['display_options']['logscale']
        logscale = []
    except:
        logscale = False
        logs = None

    try:
        masks = config[configkeys[0]]['display_options']['maskthresholds']
        maskthreshes = []
    except:
        maskthreshes = None
        masks = None

    try:
        default = \
            config[configkeys[0]]['display_options']['colors']['default']
        default = eval(default)
    except:
        default = None

    for i, key in enumerate(keys):
        plotorder += [key]
        if limits is not None:
            found = False
            for l in limits:
                getlim = None
                if l in key:
                    if type(limits[l]) is list:
                        getlim = np.array(limits[l]).astype(np.float)
                    else:
                        try:
                            getlim = eval(limits[l])
                        except:
                            getlim = None
                    lims.append(getlim)
                    found = True
            if not found:
                lims.append(None)

        if colors is not None:
            found = False
            for c in colors:
                if c in key:
                    getcol = colors[c]
                    colorobject = eval(getcol)
                    if colorobject is None:
                        colorobject = default
                    colormaps.append(colorobject)
                    found = True
            if not found:
                colormaps.append(default)

        if logs is not None:
            found = False
            for g in logs:
                getlog = False
                if g in key:
                    if logs[g].lower() == 'true':
                        getlog = True
                    logscale.append(getlog)
                    found = True
            if not found:
                logscale.append(False)

        if masks is not None:
            found = False
            for m in masks:
                if m in key:
                    getmask = eval(masks[m])
                    maskthreshes.append(getmask)
                    found = True
            if not found:
                maskthreshes.append(None)

    # Reorder everything so model is first, if it's not already
    if plotorder[0] != 'model':
        indx = [idx for idx, key in enumerate(plotorder) if key == 'model']
        if len(indx) == 1:
            indx = indx[0]
            firstpo = plotorder.pop(indx)
            plotorder = [firstpo] + plotorder
            firstlog = logscale.pop(indx)
            logscale = [firstlog] + logscale
            firstlim = lims.pop(indx)
            lims = [firstlim] + lims
            firstcol = colormaps.pop(indx)
            colormaps = [firstcol] + colormaps

    return plotorder, logscale, lims, colormaps, maskthreshes


def text_to_json(input1):
    """Simplification of text_to_json from shakelib.rupture.factory

    Args:
        input1 (str): url or filepath to text file

    Returns:
        json formatted stream of input1
    """
    if os.path.exists(input1):
        with open(input1, 'r') as f:
            lines = f.readlines()
    else:
        with urllib.request.urlopen(input1) as f:
            lines = f.readlines()

    x = []
    y = []
    z = []
    reference = ''
    # convert to geojson
    for line in lines:
        sline = line.strip()
        if sline.startswith('#'):
            reference += sline.strip('#').strip('Source: ')
            continue
        if sline.startswith('>'):
            if len(x):  # start of new line segment
                x.append(np.nan)
                y.append(np.nan)
                z.append(np.nan)
                continue
            else:  # start of file
                continue
        if not len(sline.strip()):
            continue
        parts = sline.split()

        y.append(float(parts[0]))
        x.append(float(parts[1]))
        if len(parts) >= 3:
            z.append(float(parts[2]))
        else:
            print('Fault file has no depths, assuming zero depth')
            z.append(0.0)
        coords = []
        poly = []
        for lon, lat, dep in zip(x, y, z):
            if np.isnan(lon):
                coords.append(poly)
                poly = []
            else:
                poly.append([lon, lat, dep])
        if poly != []:
            coords.append(poly)

    d = {
        "type": "FeatureCollection",
        "metadata": {
            'reference': reference
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "rupture type": "rupture extent"
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [coords]
                }
            }
        ]
    }
    return json.dumps(d)


def write_floats(filename, grid2d):
    """Create a binary (with acc. header file) version of a Grid2D object.

    Args:
        filename (str): String filename to write (i.e., 'probability.flt')
        grid2d (Grid2D): MapIO Grid2D object.

    Returns:
        Given a filename input of "probability.flt", this function will
        create that file, plus a text file called "probability.hdr".
    """
    geodict = grid2d.getGeoDict().asDict()
    array = grid2d.getData().astype('float32')
    np.save(filename, array)
    npyfilename = filename + '.npy'
    os.rename(npyfilename, filename)
    fpath, fname = os.path.split(filename)
    fbase, _ = os.path.splitext(fname)
    hdrfile = os.path.join(fpath, fbase + '.hdr')
    f = open(hdrfile, 'wt')
    for key, value in geodict.items():
        if isinstance(value, int):
            fmt = '%s = %i\n'
        elif isinstance(value, float):
            fmt = '%s = %.4f\n'
        else:
            fmt = '%s = %s\n'
        f.write(fmt % (key, value))
    f.close()


def savelayers(grids, filename):
    """
    Save ground failure layers object as a MultiHazard HDF file, preserving
    metadata structures. All layers must have same geodictionary.

    Args:
        grids: Ground failure layers object.
        filename (str): Path to where you want to save this file.

    Returns:
        .hdf5 file containing ground failure layers
    """
    layers = collections.OrderedDict()
    metadata = collections.OrderedDict()
    for key in list(grids.keys()):
        layers[key] = grids[key]['grid'].getData()
        metadata[key] = {
            'description': grids[key]['description'],
            'type': grids[key]['type'],
            'label': grids[key]['label']
        }
    origin = {}
    header = {}
    mgrid = MultiHazardGrid(layers, grids[key]['grid'].getGeoDict(),
                            origin,
                            header,
                            metadata=metadata)
    mgrid.save(filename)


def loadlayers(filename):
    """
    Load a MultiHazard HDF file back in as a ground failure layers object in
    active memory (must have been saved for this purpose).
    Args:
        filename (str): Path to layers file (hdf5 extension).

    Returns:
        Ground failure layers object
    """
    mgrid = MultiHazardGrid.load(filename)
    grids = collections.OrderedDict()
    for key in mgrid.getLayerNames():
        grids[key] = {
            'grid': mgrid.getData()[key],
            'description': mgrid.getMetadata()[key]['description'],
            'type': mgrid.getMetadata()[key]['type'],
            'label': mgrid.getMetadata()[key]['label']
        }

    return grids


def get_alert(paramalertLS, paramalertLQ, parampopLS, parampopLQ,
              hazbinLS=[1., 10., 100.], popbinLS=[100, 1000, 10000],
              hazbinLQ=[10., 100., 1000.], popbinLQ=[1000, 10000, 100000]):
    """
    Get alert levels

    Args:
        paramalertLS (float): Hazard statistic of preferred landslide model
        paramalertLQ (float): Hazard statistic of preferred liquefaction model
        parampopLS (float): Exposure statistic of preferred landslide model
        parampopLQ (float): Exposure statistic of preferred liquefaction model
        hazbinLS (list): 3 element list of bin edges for landslide
            hazard alert between Green and Yellow, Yellow and Orange, and
            Orange and Red.
        popbinLS (list): same as above but for population exposure
        hazbinLQ (list): 3 element list of bin edges for liquefaction hazard
            alert between Green and Yellow, Yellow and Orange, and Orange
            and Red.
        popbinLQ (list): same as above but for population exposure

    Returns:
        Returns:
            tuple: (hazLS, popLS, hazLQ, popLQ, LS, LQ) where:
                * hazLS: the landslide hazard alert level (str)
                * popLS: the landslide population alert level (str)
                * hazLQ: the liquefaction hazard alert level (str)
                * popLQ: the liquefaction population alert level (str)
                * LS: the overall landslide alert level (str)
                * LQ: the overall liquefaction alert level (str)

    """
    if paramalertLS is None:
        hazLS = None
    elif paramalertLS < hazbinLS[0]:
        hazLS = 'green'
    elif paramalertLS >= hazbinLS[0] and paramalertLS < hazbinLS[1]:
        hazLS = 'yellow'
    elif paramalertLS >= hazbinLS[1] and paramalertLS < hazbinLS[2]:
        hazLS = 'orange'
    elif paramalertLS > hazbinLS[2]:
        hazLS = 'red'
    else:
        hazLS = None

    if parampopLS is None:
        popLS = None
    elif parampopLS < popbinLS[0]:
        popLS = 'green'
    elif parampopLS >= popbinLS[0] and parampopLS < popbinLS[1]:
        popLS = 'yellow'
    elif parampopLS >= popbinLS[1] and parampopLS < popbinLS[2]:
        popLS = 'orange'
    elif parampopLS > popbinLS[2]:
        popLS = 'red'
    else:
        popLS = None

    if paramalertLQ is None:
        hazLQ = None
    elif paramalertLQ < hazbinLQ[0]:
        hazLQ = 'green'
    elif paramalertLQ >= hazbinLQ[0] and paramalertLQ < hazbinLQ[1]:
        hazLQ = 'yellow'
    elif paramalertLQ >= hazbinLQ[1] and paramalertLQ < hazbinLQ[2]:
        hazLQ = 'orange'
    elif paramalertLQ > hazbinLQ[2]:
        hazLQ = 'red'
    else:
        hazLQ = None

    if parampopLQ is None:
        popLQ = None
    elif parampopLQ < popbinLQ[0]:
        popLQ = 'green'
    elif parampopLQ >= popbinLQ[0] and parampopLQ < popbinLQ[1]:
        popLQ = 'yellow'
    elif parampopLQ >= popbinLQ[1] and parampopLQ < popbinLQ[2]:
        popLQ = 'orange'
    elif parampopLQ >= popbinLQ[2]:
        popLQ = 'red'
    else:
        popLQ = None

    num2color = {
        '1': 'green',
        '2': 'yellow',
        '3': 'orange',
        '4': 'red'
    }
    col2num = dict((v, k) for k, v in num2color.items())

    LSnum1 = col2num[hazLS]
    LSnum2 = col2num[popLS]
    LSnum = str(np.max([int(LSnum1), int(LSnum2)]))
    LS = num2color[LSnum]

    LQnum1 = col2num[hazLQ]
    LQnum2 = col2num[popLQ]
    LQnum = str(np.max([int(LQnum1), int(LQnum2)]))
    LQ = num2color[LQnum]

    return hazLS, popLS, hazLQ, popLQ, LS, LQ


def view_database(database, starttime=None, endtime=None,
                  minmag=None, maxmag=None, eventids=None,
                  realtime=False, currentonly=False, numevents=None,
                  LShazmin=None, LShazmax=None, LSpopmin=None,
                  LSpopmax=None, LQhazmin=None, LQhazmax=None,
                  LQpopmin=None, LQpopmax=None, verbose=False,
                  printcols=None, csvfile=None, printsummary=True,
                  printsuccess=False, printfailed=False,
                  printnotmet=False, maxcolwidth=100,
                  alertreport='value', realtime_maxsec=86400.):
    """
    Prints out information from the ground failure database based on
    search criteria and other options. If nothing is defined except the
    database, it will print out a summary and details on the successful
    event runs only.

    Args:
        database (str): file path to event database (.db file)
        starttime (str): earliest earthquake time to include in the search,
            can be any string date recognizable by np.datetime
        endtime (str): latest earthquake time to include in the search,
            can be any string date recognizable by datetime
        minmag (float): minimum magnitude to include in search
        maxmag (float): maximum magnitude to include in search
        eventids (list): list of specific event ids to include (optional)
        realtime (bool): if True, will only include events that were run in
            near real time (defined by delay time less than realtime_maxsec)
        currentonly (bool): if True, will only include the most recent run
            of each event
        numevents (int): Include the numevents most recent events that meet
            search criteria
        LShazmin: minimum landslide hazard alert color ('green', 'yellow',
            'orange', 'red') or minimum hazard alert statistic value
        LShazmax: same as above but for maximum landslide hazard alert
            value/color
        LSpopmin: same as above but for minimum landslide population alert
            value/color
        LSpopmax: same as above but for maximum landslide population alert
            value/color
        LQhazmin: same as above but for minimum liquefaction hazard alert
            value/color
        LQhazmax: same as above but for maximum liquefaction hazard alert
            value/color
        LQpopmin: same as above but for minimum liquefaction population alert
            value/color
        LQpopmax: same as above but for maximum liquefaction population alert
            value/color
        verbose (bool): if True, will print all columns (overridden if
                printcols is assigned)
        printcols (list): List of columns to print out (choose from id,
                  eventcode, shakemap_version, note, version, lat, lon, depth,
                  time, mag, location, starttime, endtime, eventdir,
                  finitefault, HaggLS, ExpPopLS, HaggLQ, ExpPopLQ
        csvfile: If defined, saves csvfile of table of all events found
            (includes all fields and failed/non-runs)
        printsummary (bool): if True (default), will print summary of events
            found to screen
        printsuccess (bool): if True (default), will print out database entries
            for successful event runs found
        printfailed (bool): if True (default False), will print out information
            about failed event runs
        printnotmet (bool): if True (default False), will print out information
            about event runs that didn't meet criteria to run ground failure
        maxcolwidth (int): maximum column width for printouts of database
            entries.
        alertreport (str): 'value' if values of alert statistics should be
            printed, or 'color' if alert level colors should be printed
        realtime_maxsec (float): if realtime is True, this is the maximum delay
            between event time and processing end time in seconds
            to consider an event to be run in realtime

    Returns:
        Prints summaries and database info to screen as requested, saves a
        csv file if requested. Also returns a tuple where (success, fail,
        notmet, stats, criteria) where
            * success: pandas dataframe of selected events that ran
                successfully
            * fail: pandas dataframe of selected events that failed to run
                due to an error
            * notmet: pandas dataframe of selected events that failed to run
                because they did not meet the criteria to run ground failure
            * stats: dictionary containing statistics summarizing selected
                events where
                * aLSg/y/o/r is the number of overall alerts of green/yellow
                    orange or red for landslides. If LS is replaced with LQ,
                    it is the same but for liquefaction.
                * hazLSg/y/o/r same as above but for hazard alert level totals
                * popLSg/y/o/r same as above but for population alert level
                    totals
                * nsuccess is the number of events that ran successfully
                * nfail is the number of events that failed to run
                * nnotmet is the number of events that didn't run because they
                    did not meet criteria to run ground failure
                * nunique is the number of unique earthquake events run
                * nunique_success is the number of unique earthquake events
                    that ran successfully
                * nrealtime is the number of events that ran in near-real-time
                * delay_median_s is the median delay time for near-real-time
                    events (earthquake time until first GF run), also the same
                    for mean, min, max, and standard deviation
            * criteria: dictionary containing info on what criteria were used
                for the search
    """
    import warnings
    warnings.filterwarnings("ignore")

    criteria = dict(locals())
    # Define alert bins for later use
    hazbinLS = dict(green=[0., 1], yellow=[1., 10.], orange=[10., 100.],
                    red=[100., 1e20])
    popbinLS = dict(green=[0., 100], yellow=[100., 1000.],
                    orange=[1000., 10000.], red=[10000., 1e20])
    hazbinLQ = dict(green=[0., 10], yellow=[10., 100.], orange=[100., 1000.],
                    red=[1000., 1e20])
    popbinLQ = dict(green=[0., 1000], yellow=[1000., 10000.],
                    orange=[10000., 100000.], red=[100000., 1e20])

    connection = None
    connection = lite.connect(database)

    pd.options.display.max_colwidth = maxcolwidth

    # Read in entire shakemap table, do selection using pandas
    df = pd.read_sql_query("SELECT * FROM shakemap", connection)

    okcols = list(df.keys())

    if eventids is not None:
        if not hasattr(eventids, '__len__'):
            eventids = [eventids]
        df = df.loc[df['eventcode'].isin(eventids)]

    if minmag is not None:
        df = df.loc[df['mag'] >= minmag]
    if maxmag is not None:
        df = df.loc[df['mag'] <= maxmag]

    df['starttime'] = pd.to_datetime(df['starttime'], utc=True)
    df['endtime'] = pd.to_datetime(df['endtime'], utc=True)
    df['time'] = pd.to_datetime(df['time'], utc=True)

    # Narrow down the database based on input criteria

    # set default values for start and end
    endt = pd.to_datetime('today', utc=True)
    stt = pd.to_datetime('1700-01-01', utc=True)
    if starttime is not None:
        stt = pd.to_datetime(starttime, utc=True)
    if endtime is not None:
        endt = pd.to_datetime(endtime, utc=True)
    df = df.loc[(df['time'] > stt) & (df['time'] <= endt)]

    # Winnow down based on alert
    # Assign numerical values if colors were used

    if LShazmin is not None or LShazmax is not None:
        if LShazmin is None:
            LShazmin = 0.
        if LShazmax is None:
            LShazmax = 1e20
        if isinstance(LShazmin, str):
            LShazmin = hazbinLS[LShazmin][0]
        if isinstance(LShazmax, str):
            LShazmax = hazbinLS[LShazmax][1]
        df = df.loc[(df['HaggLS'] >= LShazmin) & (df['HaggLS'] <= LShazmax)]

    if LQhazmin is not None or LQhazmax is not None:
        if LQhazmin is None:
            LQhazmin = 0.
        if LQhazmax is None:
            LQhazmax = 1e20
        if isinstance(LQhazmin, str):
            LQhazmin = hazbinLQ[LQhazmin][0]
        if isinstance(LQhazmax, str):
            LQhazmax = hazbinLQ[LQhazmax][1]
        df = df.loc[(df['HaggLQ'] >= LQhazmin) & (df['HaggLQ'] <= LQhazmax)]

    if LSpopmin is not None or LSpopmax is not None:
        if LSpopmin is None:
            LSpopmin = 0.
        if LSpopmax is None:
            LSpopmax = 1e20
        if isinstance(LSpopmin, str):
            LSpopmin = popbinLS[LSpopmin][0]
        if isinstance(LSpopmax, str):
            LSpopmax = popbinLS[LSpopmax][1]
        df = df.loc[(df['ExpPopLS'] >= LSpopmin) &
                    (df['ExpPopLS'] <= LSpopmax)]

    if LQpopmin is not None or LQpopmax is not None:
        if LQpopmin is None:
            LQpopmin = 0.
        if LQpopmax is None:
            LQpopmax = 1e20
        if isinstance(LQpopmin, str):
            LQpopmin = popbinLQ[LQpopmin][0]
        if isinstance(LQpopmax, str):
            LQpopmax = popbinLQ[LQpopmax][1]
        df = df.loc[(df['ExpPopLQ'] >= LQpopmin) &
                    (df['ExpPopLQ'] <= LQpopmax)]

    # Figure out which were run in real time
    delays = []
    event_codes = df['eventcode'].values
    elist, counts = np.unique(event_codes, return_counts=True)
    keep = []
    for idx in elist:
        vers = df.loc[df['eventcode'] == idx]['shakemap_version'].values
        vermin = np.nanmin(vers)
        sel1 = df.loc[(df['eventcode'] == idx) &
                      (df['shakemap_version'] == vermin)]
        delay = np.timedelta64(sel1['endtime'].values[0] -
                               sel1['time'].values[0], 's').astype(int)
        if delay <= realtime_maxsec:
            keep.append(idx)
            delays.append(delay)
        else:
            delays.append(float('nan'))

    if realtime:  # Keep just realtime events
        df = df.loc[df['eventcode'].isin(keep)]

    # Get only latest version for each event id if requested
    if currentonly:
        df.insert(0, 'Current', 0)
        ids = np.unique(df['eventcode'])
        for id1 in ids:
            # Get most recent one for each
            temp = df.loc[df['eventcode'] == id1].copy()
            temp.sort_values('endtime')
            df.loc[df['id'] == temp.iloc[-1]['id'], 'Current'] = 1
        df = df.loc[df['Current'] == 1]

    # Keep just the most recent number requested
    if numevents is not None and numevents < len(df):
        df = df.iloc[(numevents*-1):]

    # Now that have requested dataframe, make outputs
    success = df.loc[df['note'] == '']
    fail = df.loc[df['note'].str.contains('fail')]
    notmet = df.loc[(~df['note'].str.contains('fail')) & (df['note'] != '')]

    if len(df) == 0:
        print('No matching GF runs found')
        return
    cols = []
    if printcols is not None:
        for p in printcols:
            if p in okcols:
                cols.append(p)
            else:
                print('column %s defined in printcols does not exist in the '
                      'database' % p)
    elif verbose:
        cols = okcols
    else:  # List of what we usually want to see
        cols = ['eventcode', 'mag', 'location', 'time', 'shakemap_version',
                'version', 'HaggLS', 'ExpPopLS', 'HaggLQ', 'ExpPopLQ']

    # Compute overall alert stats (just final for each event)

    # get unique event code list of full database
    codes = df['eventcode'].values
    allevids, count = np.unique(codes, return_counts=True)
    nunique = len(allevids)

    # get unique event code list for success
    event_codes = success['eventcode'].values
    elist2, count = np.unique(event_codes, return_counts=True)
    nunique_success = len(elist2)
    # Get delays just for these events
    delays = np.array(delays)
    del_set = []
    for el in elist2:
        del_set.append(delays[np.where(elist == el)][0])

    # get final alert values for each
    hazalertLS = []
    hazalertLQ = []
    popalertLS = []
    popalertLQ = []
    alertLS = []
    alertLQ = []

    # Currently includes just the most current one
    for idx in elist2:
        vers = np.nanmax(success.loc[success['eventcode'] == idx]
                         ['shakemap_version'].values)
        sel1 = success.loc[(df['eventcode'] == idx) &
                           (success['shakemap_version'] == vers)]
        out = get_alert(sel1['HaggLS'].values[-1],
                        sel1['HaggLQ'].values[-1],
                        sel1['ExpPopLS'].values[-1],
                        sel1['ExpPopLQ'].values[-1])
        hazLS, popLS, hazLQ, popLQ, LS, LQ = out
        hazalertLS.append(hazLS)
        hazalertLQ.append(hazLQ)
        popalertLS.append(popLS)
        popalertLQ.append(popLQ)
        alertLS.append(LS)
        alertLQ.append(LQ)

    origsuc = success.copy()  # Keep copy

    # Convert all values to alert colors
    for index, row in success.iterrows():
        for k, bins in hazbinLS.items():
            if row['HaggLS'] >= bins[0] and row['HaggLS'] < bins[1]:
                success.loc[index, 'HaggLS'] = k
        for k, bins in hazbinLQ.items():
            if row['HaggLQ'] >= bins[0] and row['HaggLQ'] < bins[1]:
                success.loc[index, 'HaggLQ'] = k
        for k, bins in popbinLS.items():
            if row['ExpPopLS'] >= bins[0] and row['ExpPopLS'] < bins[1]:
                success.loc[index, 'ExpPopLS'] = k
        for k, bins in popbinLQ.items():
            if row['ExpPopLQ'] >= bins[0] and row['ExpPopLQ'] < bins[1]:
                success.loc[index, 'ExpPopLQ'] = k

    # Compile stats
    stats = dict(aLSg=len([a for a in alertLS if a == 'green']),
                 aLSy=len([a for a in alertLS if a == 'yellow']),
                 aLSo=len([a for a in alertLS if a == 'orange']),
                 aLSr=len([a for a in alertLS if a == 'red']),
                 hazLSg=len([a for a in hazalertLS if a == 'green']),
                 hazLSy=len([a for a in hazalertLS if a == 'yellow']),
                 hazLSo=len([a for a in hazalertLS if a == 'orange']),
                 hazLSr=len([a for a in hazalertLS if a == 'red']),
                 popLSg=len([a for a in popalertLS if a == 'green']),
                 popLSy=len([a for a in popalertLS if a == 'yellow']),
                 popLSo=len([a for a in popalertLS if a == 'orange']),
                 popLSr=len([a for a in popalertLS if a == 'red']),
                 aLQg=len([a for a in alertLQ if a == 'green']),
                 aLQy=len([a for a in alertLQ if a == 'yellow']),
                 aLQo=len([a for a in alertLQ if a == 'orange']),
                 aLQr=len([a for a in alertLQ if a == 'red']),
                 hazLQg=len([a for a in hazalertLQ if a == 'green']),
                 hazLQy=len([a for a in hazalertLQ if a == 'yellow']),
                 hazLQo=len([a for a in hazalertLQ if a == 'orange']),
                 hazLQr=len([a for a in hazalertLQ if a == 'red']),
                 popLQg=len([a for a in popalertLQ if a == 'green']),
                 popLQy=len([a for a in popalertLQ if a == 'yellow']),
                 popLQo=len([a for a in popalertLQ if a == 'orange']),
                 popLQr=len([a for a in popalertLQ if a == 'red']),
                 nsuccess=len(success),
                 nfail=len(fail),
                 nnotmet=len(notmet),
                 nruns=len(df),
                 nunique=nunique,
                 nunique_success=nunique_success,
                 nrealtime=np.sum(np.isfinite(del_set)),
                 delay_median_s=float('nan'),
                 delay_mean_s=float('nan'),
                 delay_min_s=float('nan'),
                 delay_max_s=float('nan'),
                 delay_std_s=float('nan')
                 )

    if np.sum(np.isfinite(del_set)) > 0:
        stats['delay_median_s'] = np.nanmedian(del_set)
        stats['delay_mean_s'] = np.nanmean(del_set)
        stats['delay_min_s'] = np.nanmin(del_set)
        stats['delay_max_s'] = np.nanmax(del_set)
        stats['delay_std_s'] = np.nanstd(del_set)

    # If date range not set by user
    if starttime is None:
        starttime = np.min(df['starttime'].values)
    if endtime is None:
        endtime = np.max(df['endtime'].values)

    # Now output selections in text, csv files, figures
    if csvfile is not None:
        name, ext = os.path.splitext(csvfile)
        if ext == '':
            csvfile = '%s.csv' % name
        if os.path.dirname(csvfile) == '':
            csvfile = os.path.join(os.getcwd(), csvfile)
        # make sure it's a path
        if os.path.isdir(os.path.dirname(csvfile)):
            df.to_csv(csvfile)
        else:
            raise Exception('Cannot save csv file to %s' % csvfile)

    formatters = {"time": "{:%Y-%m-%d}".format,
                  "shakemap_version": "{:.0f}".format,
                  "version": "{:.0f}".format,
                  "starttime": "{:%Y-%m-%d %H:%M}".format,
                  "endtime": "{:%Y-%m-%d %H:%M}".format}
    # Print to screen
    if stats['nsuccess'] > 0 and printsuccess:
        print('Successful - %d runs' % stats['nsuccess'])
        print('-------------------------------------------------')
        cols2 = np.array(cols).copy()
        cols2[cols2 == 'shakemap_version'] = 'shake_v'  # to save room printing
        cols2[cols2 == 'version'] = 'gf_v'  # to save room printing
        cols2[cols2 == 'time'] = 'date'  # to save room printing

        if alertreport == 'color':
            print(success.to_string(columns=cols, index=False, justify='left',
                  header=list(cols2),
                  formatters=formatters))
        else:
            print(origsuc.to_string(columns=cols, index=False, justify='left',
                  header=list(cols2),
                  formatters=formatters))
        print('-------------------------------------------------')

    if printfailed:
        if stats['nfail'] > 0:
            failcols = ['eventcode', 'location', 'mag', 'time',
                        'shakemap_version', 'note', 'starttime', 'endtime']
            failcols2 = ['eventcode', 'location', 'mag', 'time',
                         'shake_v', 'note', 'startrun', 'endrun']
#            if 'note' not in cols:
#                cols.append('note')
            print('Failed - %d runs' % stats['nfail'])
            print('-------------------------------------------------')
            print(fail.to_string(columns=failcols, index=False,
                  formatters=formatters, justify='left', header=failcols2))
        else:
            print('No failed runs found')
        print('-------------------------------------------------')

    if printnotmet:
        if stats['nnotmet'] > 0:
            failcols = ['eventcode', 'location', 'mag', 'time',
                        'shakemap_version', 'note', 'starttime', 'endtime']
            failcols2 = ['eventcode', 'location', 'mag', 'time',
                         'shake_v', 'note', 'startrun', 'endrun']
            print('Criteria not met - %d runs' % stats['nnotmet'])
            print('-------------------------------------------------')
            print(notmet.to_string(columns=failcols, index=False,
                  justify='left', header=failcols2,
                  formatters=formatters))
        else:
            print('No runs failed to meet criteria')

        print('-------------------------------------------------')

    if printsummary:
        print('Summary %s to %s' % (str(starttime)[:10], str(endtime)[:10]))
        print('-------------------------------------------------')
        print('Of total of %d events run (%d unique)' % (stats['nruns'],
              stats['nunique']))
        print('\tSuccessful: %d (%d unique)' % (stats['nsuccess'],
              stats['nunique_success']))
        print('\tFailed: %d' % stats['nfail'])
        print('\tCriteria not met: %d' % stats['nnotmet'])
        print('\tRealtime: %d' % stats['nrealtime'])
        print('\tMedian realtime delay: %1.1f mins' %
              (stats['delay_median_s']/60.,))
        print('-------------------------------------------------')
        print('Landslide overall alerts')
        print('-------------------------------------------------')
        print('Green: %d' % stats['aLSg'])
        print('Yellow: %d' % stats['aLSy'])
        print('Orange: %d' % stats['aLSo'])
        print('Red: %d' % stats['aLSr'])
        print('-------------------------------------------------')
        print('Liquefaction overall alerts')
        print('-------------------------------------------------')
        print('Green: %d' % stats['aLQg'])
        print('Yellow: %d' % stats['aLQy'])
        print('Orange: %d' % stats['aLQo'])
        print('Red: %d' % stats['aLQr'])
        print('-------------------------------------------------')
        print('Landslide hazard alerts')
        print('-------------------------------------------------')
        print('Green: %d' % stats['hazLSg'])
        print('Yellow: %d' % stats['hazLSy'])
        print('Orange: %d' % stats['hazLSo'])
        print('Red: %d' % stats['hazLSr'])
        print('-------------------------------------------------')
        print('Landslide population alerts')
        print('-------------------------------------------------')
        print('Green: %d' % stats['popLSg'])
        print('Yellow: %d' % stats['popLSy'])
        print('Orange: %d' % stats['popLSo'])
        print('Red: %d' % stats['popLSr'])
        print('-------------------------------------------------')
        print('Liquefaction hazard alerts')
        print('-------------------------------------------------')
        print('Green: %d' % stats['hazLQg'])
        print('Yellow: %d' % stats['hazLQy'])
        print('Orange: %d' % stats['hazLQo'])
        print('Red: %d' % stats['hazLQr'])
        print('-------------------------------------------------')
        print('Liquefaction population alerts')
        print('-------------------------------------------------')
        print('Green: %d' % stats['popLQg'])
        print('Yellow: %d' % stats['popLQy'])
        print('Orange: %d' % stats['popLQo'])
        print('Red: %d' % stats['popLQr'])
        print('XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')

    if alertreport == 'value':
        return origsuc, fail, notmet, stats, criteria
    else:
        return success, fail, notmet, stats, criteria


def alert_summary(database, starttime=None, endtime=None,
                  minmag=None, maxmag=None, realtime=True, currentonly=True,
                  filebasename=None,
                  summarytypes='all'):
    """
    Print summary plot of alerts that have been issued for set of events met
    by defined criteria

    Args:
        database (str): file path to event database (.db file)
        starttime (str): earliest earthquake time to include in the search,
            can be any string date recognizable by np.datetime
        endtime (str): latest earthquake time to include in the search,
            can be any string date recognizable by datetime
        minmag (float): minimum magnitude to include in search
        maxmag (float): maximum magnitude to include in search
        realtime (bool): if True, will only include events that were run in
            near real time (defined by delay time less than realtime_maxsec)
        currentonly (bool): if True, will only include the most recent run
            of each event
        filebasename (str): If defined, will save a file with a modified
            version of this name depending on which alert is displayed, if no
            path is given it will save in current directory.
        summarytypes (str): if 'all', will create three figures, one for
            overall alerts, one for hazard alerts, and one for population
            alerts. If 'overall', 'hazard', or 'population' it will create
            just the one selected.

    Returns:
        Figures showing alert level summaries

    """

    out = view_database(database, starttime=endtime, endtime=endtime,
                        minmag=minmag, maxmag=maxmag, realtime=realtime,
                        currentonly=currentonly, printsummary=False,
                        printsuccess=False, alertreport='color')
    stats = out[3]
    statsLS = []
    statsLQ = []
    types = []
    if summarytypes == 'overall' or summarytypes == 'all':
        statsLS.append([stats['aLSg'], stats['aLSy'], stats['aLSo'],
                        stats['aLSr']])
        statsLQ.append([stats['aLQg'], stats['aLQy'], stats['aLQo'],
                        stats['aLQr']])
        types.append('overall')
    if summarytypes == 'hazard' or summarytypes == 'all':
        statsLS.append([stats['hazLSg'], stats['hazLSy'], stats['hazLSo'],
                        stats['hazLSr']])
        statsLQ.append([stats['hazLQg'], stats['hazLQy'], stats['hazLQo'],
                        stats['hazLQr']])
        types.append('hazard')
    if summarytypes == 'population' or summarytypes == 'all':
        statsLS.append([stats['popLSg'], stats['popLSy'], stats['popLSo'],
                        stats['popLSr']])
        statsLQ.append([stats['popLQg'], stats['popLQy'], stats['popLQo'],
                        stats['popLQr']])
        types.append('population')

    for sLS, sLQ, typ in zip(statsLS, statsLQ, types):
        fig, ax = plt.subplots()
        index = np.arange(4)
        bar_width = 0.35
        fontsize = 12
        rects1 = ax.bar(index, sLS, bar_width,
                        alpha=0.3,
                        color='g',
                        label='Landslide Alerts')

        rects2 = ax.bar(index + bar_width, sLQ, bar_width,
                        alpha=0.7,
                        color='g',
                        label='Liquefaction Alerts')

        colors = ['g', 'y', 'orange', 'r']

        for r1, r2, c in zip(rects1, rects2, colors):
            if c == 'g':
                val = 1.00
            else:
                val = 1.05
            r1.set_color(c)
            r1.set_hatch('.')
            height = r1.get_height()
            ax.text(r1.get_x() + r1.get_width()/2., val*height,
                    '%d' % int(height),
                    ha='center', va='bottom', color=c,
                    size=fontsize-2)
            r2.set_color(c)
            r2.set_hatch('/')
            height = r2.get_height()
            ax.text(r2.get_x() + r2.get_width()/2., val*height,
                    '%d' % int(height),
                    ha='center', va='bottom', color=c,
                    size=fontsize-2)

        ax.set_xlabel('Alert', fontsize=fontsize)
        ax.set_ylabel('Total Events', fontsize=fontsize)

        ax.legend(fontsize=fontsize)

        plt.title('Ground failure %s alerts' % typ, fontsize=fontsize)
        plt.xticks(index + bar_width/2, ('Green', 'Yellow', 'Orange', 'Red'),
                   fontsize=fontsize-2)
        plt.yticks(fontsize=fontsize-2)
        plt.show()

        if filebasename is not None:
            name, ext = os.path.splitext(filebasename)
            if ext == '':
                ext = '.png'
            fig.savefig('%s_%s%s' % (name, typ, ext), bbox_inches='tight')


def time_delays(database, starttime=None, endtime=None,
                minmag=None, maxmag=None, eventids=None,
                filebasename=None, changeonly=True):
    """
    Make plot showing evolution of alerts in time
    Make a plot and print stats showing delay times and changes in alert
        statistics over time

    Args:
        database (str): file path to event database (.db file)
        starttime (str): earliest earthquake time to include in the search,
            can be any string date recognizable by np.datetime
        endtime (str): latest earthquake time to include in the search,
            can be any string date recognizable by datetime
        minmag (float): minimum magnitude to include in search
        maxmag (float): maximum magnitude to include in search
        eventids (list): list of specific event ids to include (optional)
        filebasename (str): If defined, will save a file with a modified
            version of this name depending on which alert is displayed, if no
            path is given it will save in current directory.
        changeonly (bool): if True will only show events that changed alert
            level at least once in the time evolution plots (unless eventids
            are defined, then all will show)

    Returns:
        Figures showing alert changes over time and delay and alert change
            statistics
    """
    lshbins = [0.1, 1, 10, 100, 10000]
    lspbins = [0.1, 100, 1000, 10000, 1e6]
    lqhbins = [0.3, 10, 100, 1000, 10000]
    lqpbins = [10, 1000, 10000, 100000, 1e7]
    fontsize = 10
    out = view_database(database, starttime=starttime, endtime=endtime,
                        minmag=minmag, maxmag=maxmag, realtime=True,
                        currentonly=False, printsummary=False,
                        printsuccess=False, alertreport='value',
                        eventids=eventids)

    if eventids is not None:
        changeonly = False

    success = out[0]
    elist = np.unique(success['eventcode'].values)
    HaggLS = []
    HaggLQ = []
    ExpPopLS = []
    ExpPopLQ = []
    eventtime = []
    times = []
    alertLS = []
    alertLQ = []
    descrip = []
    for idx in elist:
        sel1 = success.loc[success['eventcode'] == idx]
        hls = sel1['HaggLS'].values
        hlq = sel1['HaggLQ'].values
        pls = sel1['ExpPopLS'].values
        plq = sel1['ExpPopLQ'].values
        als = []
        alq = []
        for s, q, ps, pq in zip(hls, hlq, pls, plq):
            _, _, _, _, als1, alq1 = get_alert(s, q, ps, pq)
            als.append(als1)
            alq.append(alq1)
        alertLS.append(als)
        alertLQ.append(alq)
        HaggLS.append(hls)
        HaggLQ.append(hlq)
        ExpPopLS.append(pls)
        ExpPopLQ.append(plq)
        times.append(sel1['endtime'].values)
        eventtime.append(sel1['time'].values[-1])
        temp = success.loc[success['eventcode'] == idx]
        date = str(temp['time'].values[-1]).split('T')[0]
        descrip.append('M%1.1f %s (%s)' % (temp['mag'].values[-1],
                       temp['location'].values[-1].title(), date))

    # Plot of changes over time to each alert level
    fig1, axes = plt.subplots(2, 1)  # , figsize=(10, 10))
    ax1, ax2 = axes
    ax1.set_title('Landslide Summary Statistics', fontsize=fontsize)
    ax1.set_ylabel(r'Area Exposed to Hazard ($km^2$)', fontsize=fontsize)
    ax2.set_ylabel('Population Exposure', fontsize=fontsize)

    fig2, axes = plt.subplots(2, 1)  # , figsize=(10, 10))
    ax3, ax4 = axes
    ax3.set_title('Liquefaction Summary Statistics', fontsize=fontsize)
    ax3.set_ylabel(r'Area Exposed to Hazard ($km^2$)', fontsize=fontsize)
    ax4.set_ylabel('Population Exposure', fontsize=fontsize)

    ax2.set_xlabel('Hours after earthquake', fontsize=fontsize)
    ax4.set_xlabel('Hours after earthquake', fontsize=fontsize)

    lqplot = 0
    lsplot = 0
    lsch = 0
    lqch = 0
    mindel = []
    delstableLS = []
    delstableLQ = []
    ratHaggLS = []
    ratHaggLQ = []
    ratPopLS = []
    ratPopLQ = []
    zipped = zip(HaggLS, HaggLQ, ExpPopLS, ExpPopLQ, alertLS, alertLQ,
                 descrip, elist, times, eventtime)
    for hls, hlq, pls, plq, als, alq, des, el, t, et in zipped:
        resS = np.unique(als)
        resL = np.unique(alq)
        delays = [np.timedelta64(t1 - et, 's').astype(float) for t1 in t]
        mindel.append(np.min(delays))
        delstableLS.append(delays[np.min(np.where(np.array(als) == als[-1]))])
        delstableLQ.append(delays[np.min(np.where(np.array(alq) == alq[-1]))])
        # Set to lower edge of green bin if zero so ratios will show up
        hls = np.array(hls)
        hls[hls == 0.] = 0.1
        ratHaggLS.append(hls[-1]/hls[0])
        hlq = np.array(hlq)
        hlq[hlq == 0.] = 1.
        ratHaggLQ.append(hlq[-1]/hlq[0])
        pls = np.array(pls)
        pls[pls == 0.] = 10.
        ratPopLS.append(pls[-1]/pls[0])
        plq = np.array(plq)
        plq[plq == 0.] = 100.
        ratPopLQ.append(plq[-1]/plq[0])
        if (len(resS) > 1 or 'green' not in resS) and\
           (len(resL) > 1 or 'green' not in resL):
            if len(resS) > 1 or not changeonly:
                ax1.loglog(np.array(delays)/3600., hls, '.-', label=des)
                ax2.loglog(np.array(delays)/3600., pls, '.-')
                if changeonly:
                    lsch += 1
                lsplot += 1
            if len(resL) > 1 or not changeonly:
                ax3.loglog(np.array(delays)/3600., hlq, '.-', label=des)
                ax4.loglog(np.array(delays)/3600., plq, '.-')
                if changeonly:
                    lqch += 1
                lqplot += 1
    print('%d of %d events had a liquefaction overall alert that changed' %
          (lqch, len(elist)))
    print('%d of %d events had a landslide overall alert that changed' %
          (lsch, len(elist)))

    if lsplot < 5:
        ax1.legend(fontsize=fontsize-3)
    if lqplot < 5:
        ax3.legend(fontsize=fontsize-3)
    ax1.tick_params(labelsize=fontsize-2)
    ax2.tick_params(labelsize=fontsize-2)
    ax3.tick_params(labelsize=fontsize-2)
    ax4.tick_params(labelsize=fontsize-2)
    ax1.grid(True)
    ax2.grid(True)
    ax3.grid(True)
    ax4.grid(True)

    alert_rectangles(ax1, lshbins)
    alert_rectangles(ax2, lspbins)
    alert_rectangles(ax3, lqhbins)
    alert_rectangles(ax4, lqpbins)

    if filebasename is not None:
        name, ext = os.path.splitext(filebasename)
        if ext == '':
            ext = '.png'
        fig1.savefig('%s_LSalert_evolution%s' % (name, ext),
                     bbox_inches='tight')
        fig2.savefig('%s_LQalert_evolution%s' % (name, ext),
                     bbox_inches='tight')
    # Don't bother making this plot when eventids are specified
    if eventids is None or len(eventids) > 25:
        # Histograms of delay times etc.
        fig, axes = plt.subplots(2, 2, figsize=(10, 10), sharey='col')
        ax1 = axes[0, 0]
        bins = np.logspace(np.log10(0.1), np.log10(1000.), 15)
        ax1.hist(np.array(mindel)/3600., color='k', edgecolor='k', alpha=0.5,
                 bins=bins)

        ax1.set_xscale("log")
        ax1.set_xlabel('Time delay to first run (hours)')
        ax1.set_ylabel('Number of events')
        vals = (np.nanmean(mindel)/3600., np.nanmedian(mindel)/3600.,
                np.nanstd(mindel)/3600.)
        ax1.text(0.8, 0.8, 'mean: %1.1f hr\nmedian: %1.1f hr\nstd: %1.1f hr' %
                 vals, transform=ax1.transAxes, ha='center', va='center')
        delstableLS = np.array(delstableLS)
        delstableLQ = np.array(delstableLQ)
        delstable = np.max([delstableLS, delstableLQ], axis=0)

        ax2 = axes[1, 0]
        ax2.hist(np.array(delstable)/3600., color='k', edgecolor='k',
                 alpha=0.5, bins=bins)
        ax2.set_xscale("log")
        ax2.set_xlabel('Time delay till final alert value reached (hours)')
        ax2.set_ylabel('Number of events')
        vals = (np.nanmean(delstable)/3600., np.nanmedian(delstable)/3600.,
                np.nanstd(delstable)/3600.)
        ax2.text(0.8, 0.8, 'mean: %1.1f hr\nmedian: %1.1f hr\nstd: %1.1f hr' %
                 vals, transform=ax2.transAxes, ha='center', va='center')

        print('Liquefaction overall alerts that changed stablized after a '
              'median of %1.2f hours' %
              (np.median(delstableLQ[delstableLQ > 0.])/3600.))
        print('Landslide overall alerts that changed stablized after a median '
              'of %1.2f hours' %
              (np.median(delstableLS[delstableLS > 0.])/3600.))

        ratHaggLS = np.array(ratHaggLS)
        ratHaggLQ = np.array(ratHaggLQ)
        ax3 = axes[0, 1]
        bins = np.logspace(np.log10(0.01), np.log10(100.), 9)
        ax3.hist(ratHaggLS[ratHaggLS != 1.], hatch='.', edgecolor='k',
                 alpha=0.5, fill=False, label='Landslides',
                 bins=bins)
        ax3.hist(ratHaggLQ[ratHaggLQ != 1.], hatch='/', edgecolor='k',
                 alpha=0.5, fill=False, label='Liquefaction',
                 bins=bins)
        ax3.set_xscale("log")
        ax3.set_xlabel(r'$H_{agg}$ final/$H_{agg}$ initial')
        ax3.set_ylabel('Number of events')
        ax3.axvline(1., lw=2, color='k')
        arrowprops = dict(facecolor='black', width=1., headwidth=7.,
                          headlength=7.)
        ax3.annotate('No change:\nLS=%d\nLQ=%d' %
                     (len(ratHaggLS[ratHaggLS == 1.]),
                      len(ratHaggLQ[ratHaggLQ == 1.])),
                     xy=(0.5, 0.6), xycoords='axes fraction',
                     textcoords='axes fraction', ha='center', va='center',
                     xytext=(0.3, 0.6),
                     arrowprops=arrowprops)
        ax3.legend(handlelength=2, handleheight=3, loc='upper right')

        ratPopLS = np.array(ratPopLS)
        ratPopLQ = np.array(ratPopLQ)
        ax4 = axes[1, 1]
        bins = np.logspace(np.log10(0.01), np.log10(100.), 9)
        ax4.hist(ratPopLS[ratPopLS != 1.], hatch='.', edgecolor='k',
                 alpha=0.5, fill=False, bins=bins)
        ax4.hist(ratPopLQ[ratPopLQ != 1.], bins=bins,
                 hatch='/', edgecolor='k', alpha=0.5, fill=False)
        ax4.set_xscale("log")
        ax4.set_xlabel(r'$Pop_{exp}$ final/$Pop_{exp}$ initial')
        ax4.set_ylabel('Number of events')
        ax4.axvline(1., lw=2, color='k')
        ax4.annotate('No change:\nLS=%d\nLQ=%d' %
                     (len(ratPopLS[ratPopLS == 1.]),
                      len(ratPopLQ[ratPopLQ == 1.])),
                     xy=(0.5, 0.75), xycoords='axes fraction',
                     textcoords='axes fraction', xytext=(0.3, 0.75),
                     arrowprops=arrowprops, ha='center', va='center')

        # Add letters
        ax1.text(0.02, 0.98, 'a)', transform=ax1.transAxes, ha='left',
                 va='top', fontsize=14)
        ax2.text(0.02, 0.98, 'b)', transform=ax2.transAxes, ha='left',
                 va='top', fontsize=14)
        ax3.text(0.02, 0.98, 'c)', transform=ax3.transAxes, ha='left',
                 va='top', fontsize=14)
        ax4.text(0.02, 0.98, 'd)', transform=ax4.transAxes, ha='left',
                 va='top', fontsize=14)

        plt.show()
        if filebasename is not None:
            name, ext = os.path.splitext(filebasename)
            fig.savefig('%s_alertdelay_stats%s' % (name, ext),
                        bbox_inches='tight')


def alert_rectangles(ax, bins):
    """
    Function used to color bin levels in background of axis
    """
    colors = ['g', 'yellow', 'orange', 'r']
    xlims = ax.get_xlim()
    ylims = ax.get_ylim()
    for i, col in enumerate(colors):
        y = bins[i]
        y2 = bins[i+1]
        if col == 'g':
            corners = [[xlims[0], ylims[0]], [xlims[0], y2], [xlims[1], y2],
                       [xlims[1], ylims[0]]]
        elif col == 'r':
            corners = [[xlims[0], y], [xlims[0], ylims[1]],
                       [xlims[1], ylims[1]], [xlims[1], y]]
        else:
            corners = [[xlims[0], y], [xlims[0], y2], [xlims[1], y2],
                       [xlims[1], y]]
        # add rectangle
        rect = patches.Polygon(corners, closed=True, facecolor=col,
                               transform=ax.transData, alpha=0.2)
        ax.add_patch(rect)
