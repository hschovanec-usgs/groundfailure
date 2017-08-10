# #!/usr/bin/env python

# #lib imports
# import os.path
# import warnings
# import urllib.request, urllib.error, urllib.parse
# import tempfile
# import collections
# import math
# import numpy as np

# #local imports
# from mapio.shake import ShakeGrid
# from mapio.gdal import GDALGrid
# from mapio.geodict import GeoDict

# config = {'statistical_models': {'kritikos_2015': {'gamma_value': 0.9, 'layers': {'slope': '/Users/kbiegel/Documents/GroundFailure/Codes/Slopes/Northridge_Slopes/Northridge_SLP_WGS84_3arcsec.bil', 'dff': '', 'dfs': '', 'elev': '/Users/kbiegel/Documents/GroundFailure/Codes/model_inputs/global_gted_meanelev_30c.flt'}, 'thresholds': {'slope': 3, 'elev': 50, 'loc': 9}, 'divisor': {'MMI': 7.5, 'slope': 4.875, 'dff': 2.375, 'dfs': 3.25, 'slope_pos': 2.325}, 'power': {'MMI': -14, 'slope': -2.65, 'dff': 5.375, 'dfs': 5.5, 'slope_pos': -4.375}, 'classification': {'MMI': '5, 6, 7, 8, 9', 'slope': '0-4, 5-9, 10-14, 15-19, 20-24, 25-29, 30-34, 35-39, 40-44, 45-49, 50', 'dff': '0-4, 5-9, 10-19, 20-29, 30-39, 40-49, 50', 'dfs': '0-0.49, 0.5-0.99, 1.0-1.49, 1.5-1.99, 2.0-2.49, 2.5', 'slope_pos': 'Flat, Valley, Mid-Slope, Ridge'}}}}
# shakefile = '/Users/kbiegel/Documents/GroundFailure/Codes/Shakefiles/Northridge.xml'


# def create_slopePos(slope, DEM, cmodel):
#     """
#     Takes the slope and elevation files and outputs a slope-pos file with classifications: valley, lower slope, mid-slope, flat,
#     upper slope, ridge.
#     """
#     # Double check the shapes are the same
#     a, b = DEM.shape
#     c, d = slope.shape
#     if a != c or b != d:
#         raise NameError('DEM and slope are not the same shape.')
#     slopethresh = cmodel['thresholds']['slope']
#     elevthresh = cmodel['thresholds']['elev']
#     locthresh = cmodel['thresholds']['loc']

#     # Take a moving average over DEM
#     DEM_avg = np.empty((a, b))
#     DEM_avg[:] = np.NAN
#     for i in range(locthresh, a-locthresh):
#         for j in range(locthresh, b-locthresh):
#             e = i-locthresh
#             f = i+locthresh
#             g = j-locthresh
#             h = j+locthresh
#             summ = 0
#             count = 0
#             try:
#                 for k in range(e,f+1):
#                     for l in range(g,h+1):
#                         summ += DEM[k,l]
#                         count += 1
#                 DEM_avg[i,j] = summ/count
#             except:
#                 raise NameError('Could not take average.')
#     print(DEM_avg)

#     # Classify DEM into regions
#     DEM_comp = DEM - DEM_avg
#     print(DEM_comp)
#     DEM_classified = np.empty((a, b), dtype=object)
#     DEM_classified[:] = np.nan
#     for i in range(0,a):
#         for j in range(0,b):
#             if not np.isnan(DEM_comp[i,j]):
#                 if DEM_comp[i,j] < -elevthresh:
#                     if slope[i,j] <= slopethresh:
#                         DEM_classified[i,j] = 'Valley'
#                     else:
#                         DEM_classified[i,j] = 'Mid-Slope'
#                 elif DEM_comp[i,j] > -elevthresh and DEM_comp[i,j] < elevthresh:
#                     if slope[i,j] <= slopethresh:
#                         DEM_classified[i,j] = 'Flat'
#                     else:
#                         DEM_classified[i,j] = 'Mid-Slope'
#                 elif DEM_comp[i,j] > elevthresh:
#                     if slope[i,j] <= slopethresh:
#                         DEM_classified[i,j] = 'Ridge'
#                     else:
#                         DEM_classified[i,j] = 'Mid-Slope'
#     print(DEM_classified)

#     return DEM_classified


# def kritikos_fuzzygamma(shakefile, config, bounds=None):
#     """
#     Runs kritikos procedure with fuzzy gamma overlay method
#     """

#     cmodel = config['statistical_models']['kritikos_2015']
#     gamma = cmodel['gamma_value']

#     ## Read in layer files and get data
#     layers = cmodel['layers']
#     try:
#         # Slope
#         slope_file = layers['slope']
#         # DFF
#         dff_file = layers['dff']
#         # DFS
#         dfs_file = layers['dfs']
#         # elev
#         elev_file = layers['elev']
#     except:
#         print('Unable to retrieve grid data.')

#     try:
#         div = cmodel['divisor']
#         # Load in divisors
#         MMI_div = div['MMI']
#         slope_div = div['slope']
#         dff_div = div['dff']
#         dfs_div = div['dfs']
#         slope_pos_div = div['slope_pos']
#     except:
#         print('Unable to retrieve divisors.')

#     try:
#         power = cmodel['power']
#         # Load in powers
#         MMI_power = power['MMI']
#         slope_power = power['slope']
#         dff_power = power['dff']
#         dfs_power = power['dfs']
#         slope_pos_power = power['slope_pos']
#     except:
#         print('Unable to retrieve powers.')

#     # Cut and resample all files
#     try:
#         bounds = None
#         shkgdict = ShakeGrid.getFileGeoDict(shakefile, adjust='res')
#         slopedict, duplicated = GDALGrid.getFileGeoDict(slope_file)
#         if bounds is not None:  # Make sure bounds are within ShakeMap Grid
#             if shkgdict.xmin > bounds['xmin'] or shkgdict.xmax < bounds['xmax'] or shkgdict.ymin > bounds['ymin'] or shkgdict.ymax < bounds['ymax']:
#                 print('Specified bounds are outside shakemap area, using ShakeMap bounds instead')
#                 bounds = None
#         if bounds is not None:
#             tempgdict = GeoDict({'xmin': bounds['xmin'], 'ymin': bounds['ymin'], 'xmax': bounds['xmax'], 'ymax': bounds['ymax'], 'dx': 100., 'dy': 100., 'nx': 100., 'ny': 100.}, adjust='res')
#             gdict = slpdict.getBoundsWithin(tempgdict)
#         else:  # Get boundaries from shakemap if not specified
#             gdict = slopedict.getBoundsWithin(shkgdict)
#     except:
#         raise NameError('Unable to create base geodict.')

#     # Load in data
#     try:
#         # Load in slope data
#         slopegrid = GDALGrid.load(slope_file, samplegeodict=gdict, resample=False)
#         slope_data = slopegrid.getData().astype(float)
#         # Load in MMI
#         shakemap = ShakeGrid.load(shakefile, samplegeodict=gdict, resample=True, method='linear', adjust='res')
#         MMI_data = shakemap.getLayer('mmi').getData().astype(float)
#         # Load in Dff
#         dffgrid = GDALGrid.load(dff_file, samplegeodict=gdict, resample=False)
#         dff_data = dffgrid.getData().astype(float)
#         # Load in DFS
#         dfsgrid = GDALGrid.load(dfs_file, samplegeodict=gdict, resample=False)
#         dfs_data = dfsgrid.getData().astype(float)
#         # Load in Slope Position
#         elev_grid = GDALGrid.load(elev_file, samplegeodict=gdict, resample=False)
#         DEM = elev_grid.getData().astype(float)
#     except:
#         print('Data could not be retrieved.')

#     try:
#         mmi_class = cmodel['classification']['MMI']
#         slope_class = cmodel['classification']['slope']
#         dff_class = cmodel['classification']['dff']
#         dfs_class = cmodel['classification']['dfs']
#         slope_pos_class = cmodel['classification']['slope_pos']
#     except:
#         print('Could not recover classifications from config.')

#     try:
#         slope_pos_data = create_slopePos(slope_data, DEM, cmodel)
#     except:
#         print('Could not create slope position grid.')

#     try:
#         mmi_classes = mmi_class.split(',')
#         for i in mmi_classes:
#             if i.find('-') != -1:
#                 j = i.split('-')
#                 if MMI_data in range(int(j[0]), int(j[1])):
#                     MMI_data = int(j[0])
#             else:
#                 MMI_data = int(i)
#     except:
#         print('Could not categorize MMI values')

#     try:
#         slope_classes = slope_class.split(',')
#         k = 1
#         for i in mmi_classes:
#             if i.find('-') != -1:
#                 j = i.split('-')
#                 if slope_data in range(int(j[0]), int(j[1])):
#                     slope_data = k
#                     k += 1
#             else:
#                 slope_data = 11
#     except:
#         print('Could not recategorize Slope Values.')

#     try:
#         dff_classes = dff_class.split(',')
#         k = 1
#         for i in dff_classes:
#             if i.find('-') != -1:
#                 j = i.split('-')
#                 if dff_data in range(int(j[0]), int(j[1])):
#                     dff_data = k
#                     k += 1
#             else:
#                 dff_data = 7
#     except:
#         print('Could not recategorize DFF values.')

#     try:
#         dfs_classes = dfs_class.split(',')
#         k = 1
#         for i in dfs_classes:
#             if i.find('-') != -1:
#                 j = i.split('-')
#                 if dfs_data in range(int(j[0]), int(j[1])):
#                     dfs_data = k
#                     k += 1
#             else:
#                 dfs_data = 6
#     except:
#         print('Could not recategorize DFS values.')

#     try:
#         slope_pos_classes = slope_pos_class.split(',')
#         k = 1
#         for i in slope_poss_classes:
#             if slope_pos_data == i:
#                 slope_pos_data = k
#                 k += 1
#     except:
#         print('Could not recategorize slope position values.')

#     try:
#         layers = []
#         # Calculate layers
#         slope = 1/(1+np.exp(slope_data/slope_div, slope_power))
#         MMI = 1/(1+np.exp(MMI_data/MMI_div, MMI_power))
#         dff = 1/(1+np.exp(dff_data/dff_div, dff_power))
#         dfs = 1/(1+np.exp(dfs_data/dfs_div, dfs_power))
#         slope_pos = 1/(1+np.exp(slop_pos_data/slop_pos_div, slope_pos_power))
#         # Add to layers list (to be used in further calculations)
#         layers.append(slope)
#         layers.append(MMI)
#         layers.append(dff)
#         layers.append(dfs)
#         layers.append(slope_pos)
#     except:
#         print('Layer calculations failed.')

    # try:
    #     # Calculate final model
    #     for l in layers.items():

    #     mu_x = (pi_operator(mu_i, 1, n))^(1-gamma) * (1 - pi_operator(1-mu_i, 1, n))^(gamma)
    #     # pi_operator is a multiplication summation
