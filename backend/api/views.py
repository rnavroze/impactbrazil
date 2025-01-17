import json
from datetime import datetime
from pkgutil import get_data

from builtins import str

import requests
from django.core import serializers
from django.db.models import Max, Q
from django.shortcuts import render, get_object_or_404
from rest_framework import status, generics, exceptions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.serializers import ValidationError

from api.gisconnector.apicall import gis_get_data, gis_get
from api.models import *
from api.serializers import *


# Get the list of entities, prioritizing country partners
class EntityList(APIView):
    def get(self, request, format=None):
        # Get entity list
        gis_list = Entity.objects.all().order_by('entity_name')

        # Get country partners
        entity_partners_list = []
        for entity in EntityPartner.objects.all():
            entity_partners_list.append(entity.entity_name)

        # We will build 2 dicts, one of entity partners and one of all other entities, then merge them
        gis_list_partners = []
        gis_list_others = []

        for entity in gis_list:
            if entity.entity_name in entity_partners_list:
                gis_list_partners.append({"id": entity.gis_id, "name": entity.entity_name})
            else:
                gis_list_others.append({"id": entity.gis_id, "name": entity.entity_name})

        # Merge the two lists, keeping entity partners on top
        gis_list = gis_list_partners + gis_list_others

        return Response(gis_list)


# Get the list of opportunities by parameter
class OpportunityList(APIView):
    def get(self, request, format=None):
        # We don't actually need entity here, commenting this out for now
        entity = self.request.query_params.get('entity', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        lc = self.request.query_params.get('lc', None)
        product = self.request.query_params.get('product', None)
        q = self.request.query_params.get('q', None)
        all_opps = self.request.query_params.get('all_opps', False)

        # Product must be specified, do we really need to do this? Commented out
        # if product is None and lc is None:
        #    raise exceptions.ParseError('Either product or lc must be specified')

        # Prevent opportunities that have closed from showing
        today = datetime.now()

        sdg = self.request.query_params.get('sdg', None)
        subproduct = self.request.query_params.get('subproduct', None)

        if product is not None and (int(product) == 1 and subproduct is not None):
            raise exceptions.ParseError('subproduct not supported with this product')

        elif product is not None and (int(product) != 1 and sdg is not None):
            raise exceptions.ParseError('sdg not supported with this product')

        # Build a list of one opportunity per LC, that opportunity will be the one satisfying all conditions and having
        # the highest number of available_openings

        # Check the entity against the product
        if entity is not None and product is not None:
            try:
                no_visa = VisaDenial.objects.get(entity=int(entity), product=int(product))
                return Response({'no_visa': True})
            except VisaDenial.DoesNotExist:
                pass

        # First, get all valid opportunities, then apply filters
        opportunities_list = Opportunity.objects.filter(close_date__gt=today)

        if product is not None:
            opportunities_list = opportunities_list.filter(product__gis_id=product)

        if start_date is not None:
            opportunities_list = opportunities_list.filter(start_date__gte=start_date)

        if end_date is not None:
            opportunities_list = opportunities_list.filter(start_date__lte=end_date)

        if lc is not None:
            opportunities_list = opportunities_list.filter(lc__gis_id=lc)

        # The above check should have taken care of subproduct vs sdg anyway, so we don't need to check again
        if sdg is not None:
            opportunities_list = opportunities_list.filter(sdg__gis_id=sdg)

        if subproduct is not None:
            opportunities_list = opportunities_list.filter(subproduct__gis_id=subproduct)

        # Finally, run the 'q'
        if q is not None:
            opportunities_list = opportunities_list.filter(
                Q(title__icontains=q) | Q(lc__reference_name__icontains=q) | Q(product__name__icontains=q) | Q(
                    sdg__name__icontains=q) | Q(subproduct__name__icontains=q) | Q(organization_name__icontains=q) | Q(
                    location__icontains=q) | Q(lc__city__name__icontains=q))
            # search=SearchVector('title', 'lc__reference_name', 'product__name', 'sdg__name', 'subproduct__name',
            #                     'organization_name', 'location')).filter(search=q)

        # The below logic is only if LC is not specified
        if lc is None:
            # Only if all_opps is False do we filter one unique opportunity per LC
            if all_opps is False:
                opportunities_list = opportunities_list.distinct('lc_id').order_by('lc_id', '-available_openings')

            # Reorder according to focus in reverse so we iterate through it backwards
            focus_qs = Focus.objects.filter(product__gis_id=product).order_by('-rank').values('lc__id')
            focuses = []

            # Also reorder according to analytics, but remember that if lc1 in focus f1 > lc2 in focus f2
            # but lc in focus k2 has n2 approvals < n1 approvals of lc1, then we still show lc1 > lc2 because
            # focus is more important than approvals
            analytics_qs = Analytic.objects.filter(product__gis_id=product).order_by('number').values('lc__id')
            analytics = []

            # We need to build the lists
            for focus in focus_qs:
                focuses.append(focus['lc__id'])

            for analytic in analytics_qs:
                analytics.append(analytic['lc__id'])

            # Build final list
            opportunities_list_ordered = list(opportunities_list)

            for rankparam in [analytics, focuses]:
                for rank in rankparam:
                    for opportunity in opportunities_list:
                        if opportunity.lc_id == rank:
                            opportunities_list_ordered.remove(opportunity)
                            opportunities_list_ordered = [opportunity] + opportunities_list_ordered
        else:
            opportunities_list_ordered = list(opportunities_list.order_by('-available_openings', 'close_date'))

        return Response(OpportunitySerializer(opportunities_list_ordered, many=True).data)


# Get list of LCs
class LCList(generics.ListAPIView):
    queryset = LC.objects.filter(hidden=False).order_by('reference_name')
    serializer_class = LCSerializer


# Get details of LC
class LCDetails(generics.RetrieveAPIView):
    lookup_field = 'gis_id'
    queryset = LC.objects.all()
    serializer_class = LCSerializer


# Get list of products
class ProductList(generics.ListAPIView):
    queryset = Product.objects.all().order_by('gis_id')
    serializer_class = ProductSerializer


# Get list of subproducts
class SubproductList(generics.ListAPIView):
    def get_queryset(self):
        product = self.request.query_params.get('product', None)

        if product is None:
            return Subproduct.objects.filter(hidden=False).order_by('order')
        else:
            return Subproduct.objects.filter(hidden=False, product__gis_id=product).order_by('order')

    serializer_class = SubproductSerializer


# Get details of subproduct
class SubproductDetail(generics.RetrieveAPIView):
    lookup_field = 'gis_id'
    queryset = Subproduct.objects.all()
    serializer_class = SubproductSerializer


# Get list of SDGs
class SDGList(generics.ListAPIView):
    queryset = SDG.objects.filter(hidden=False).order_by('number')
    serializer_class = SDGSerializer


# Get details of SDG
class SDGDetail(generics.RetrieveAPIView):
    lookup_field = 'number'
    queryset = SDG.objects.all()
    serializer_class = SDGSerializer


# Get list of Projects
class ProjectList(generics.ListAPIView):
    queryset = Project.objects.order_by('order')
    serializer_class = ProjectSerializer


# Get details of Project
class ProjectDetail(generics.RetrieveAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


# Get list of entity partners
class EntityPartnerList(generics.ListAPIView):
    queryset = EntityPartner.objects.all()
    serializer_class = EntityPartnerSerializer


# Get list of entity partners
class EntityPartnerDetails(APIView):
    def get(self, request, format=None, pk=0):
        try:
            entity = EntityPartner.objects.get(gis_id=pk)
            is_partner = True
        except EntityPartner.DoesNotExist:
            entity = get_object_or_404(Entity.objects.all(), gis_id=pk)
            is_partner = False

        partnership_details = {"id": entity.id, "gis_id": entity.gis_id, "name": entity.entity_name,
                               "is_partner": is_partner, "video": None, "thumbnail": None}

        if is_partner:
            partnership_details['video'] = entity.video_link
            partnership_details['thumbnail'] = entity.thumbnail

        return Response(partnership_details)


# Get list of cities
class CityList(generics.ListAPIView):
    queryset = City.objects.all().order_by('name')
    serializer_class = CitySerializerMini


class CityDetail(generics.RetrieveAPIView):
    queryset = City.objects.all()
    serializer_class = CitySerializer


class CityByName(APIView):
    def get(self, request, format=None, name=''):
        converted_name = name.replace("-", " ")
        found_city = get_object_or_404(City.objects.all(), name_unaccented__iexact=converted_name)
        return Response(CitySerializer(found_city).data)


class LCByName(APIView):
    def get(self, request, format=None, name=''):
        converted_name = name.replace("-", " ")
        found_city = get_object_or_404(LC.objects.all(), unaccented_name__iexact=converted_name)
        return Response(LCSerializer(found_city).data)


# Get list of regions
class RegionList(generics.ListAPIView):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer


# Login with API
class Login(APIView):
    def post(self, request, format=None):
        from api.gisconnector.userauth import yop_login
        import json

        attrs = json.loads(request.body)

        try:
            success, token = yop_login(attrs['username'], attrs['password'])
        except KeyError:
            return Response({"error": "MISSING_PARAMS"}, status=status.HTTP_400_BAD_REQUEST)

        if success:
            return Response({"access_token": token})
        else:
            return Response({"error": token}, status=status.HTTP_401_UNAUTHORIZED)


# Apply to an opportunity
class Apply(APIView):
    def post(self, request, format=None):
        from api.gisconnector.apicall import yop_apply_opportunity
        import json

        attrs = json.loads(request.body)

        try:
            gip_answer = attrs['gip_answer']
            if gip_answer == '':
                gip_answer = None
        except KeyError:
            gip_answer = None

        try:
            user_id = attrs['user_id']
            if user_id == '':
                user_id = None
        except KeyError:
            user_id = None

        try:
            success, response = yop_apply_opportunity(attrs['api_key'], attrs['opp_id'], gip_answer, user_id)
        except KeyError:
            return Response({"error": "MISSING_PARAMS"}, status=status.HTTP_400_BAD_REQUEST)

        if success:
            return Response({"success": True, "response": response})
        else:
            try:
                response_dict = json.loads(response)
                if response_dict['error_code'] == 'E_INCOMPLETE_PROFILE':
                    return Response({"error": "Incomplete profile"}, status=status.HTTP_403_FORBIDDEN)
                else:
                    return Response({"error": "Error", "response": response},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except KeyError:
                if response.find("expired token") > -1:
                    return Response({"error": "Expired token"}, status=status.HTTP_401_UNAUTHORIZED)

                return Response({"error": "Error", "response": response},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Get the IP address
class IP(APIView):
    def get(self, request, format=None):
        from django.contrib.gis.geoip2 import GeoIP2
        import os
        from backend.settings import BASE_DIR
        from ipware import get_client_ip

        g = GeoIP2(path=os.path.join(BASE_DIR, 'api', 'geoipdata'))
        ip, is_routable = get_client_ip(request)

        if ip is None:
            return Response({"country": "Unknown", "ip": None})
        else:
            if is_routable:
                return Response({"country": g.country(ip)['country_name'], "ip": ip})
            else:
                return Response({"country": "Private", "ip": ip})


# Get an opportunity, if cached then get it from the cache, if not then refresh
# TODO: Second view that clears caches
class OpportunityGIS(APIView):
    def get(self, request, format=None, pk=0):
        if pk == 0:
            return Response({'error': "Opportunity ID is compulsory."},
                            status=status.HTTP_400_BAD_REQUEST)

        get_opportunity_gql = "get_opportunity.gql"
        from_cache = False

        try:
            opp_request = OpportunityCache.objects.get(opp_id=pk)
            opp_data = json.loads(opp_request.opp_json)
            from_cache = True
        except OpportunityCache.DoesNotExist:
            try:
                opp_request = gis_get(get_data("api.gql", get_opportunity_gql).decode("utf-8"),
                                      variables={'id': pk, 'cdn_links': True})
                opp_data = opp_request
            except Exception as e:
                if str(e).find("404") > -1:
                    return Response({'error': "Opportunity not found"}, status=status.HTTP_404_NOT_FOUND)
                elif str(e).find("401") > -1:
                    return Response({'error': 'Access token expired'}, status=status.HTTP_401_UNAUTHORIZED)
                else:
                    return Response(
                        {'error': "There was a problem getting the opportunity from the GIS.", 'e_text': str(e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Save this to the database
            opp = OpportunityCache(opp_id=pk, opp_json=json.dumps(opp_data))
            opp.save()

        opp_data['from_cache'] = from_cache
        return Response(opp_data)


class OpportunityGISRefreshCache(APIView):
    def get(self, request, format=None, pk=0):
        try:
            opp_request = OpportunityCache.objects.get(opp_id=pk)
            opp_data_cached = opp_request.opp_json
        except OpportunityCache.DoesNotExist:
            return Response({'cache_status': "NO_CACHE"})

        get_opportunity_gql = "get_opportunity.gql"

        try:
            opp_request = gis_get(get_data("api.gql", get_opportunity_gql).decode("utf-8"),
                                  variables={'id': pk, 'cdn_links': True})
            opp_data = opp_request
        except Exception as e:
            if str(e).find("401") == -1:
                return Response(
                    {'error': "There was a problem getting the opportunity from the GIS.", 'e_text': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response({'error': 'Access token expired'}, status=status.HTTP_401_UNAUTHORIZED)

        # Save this to the database
        OpportunityCache.objects.update_or_create(opp_id=pk, defaults={'opp_json': json.dumps(opp_data)})

        # Return whether it was changed or not
        if opp_data_cached != json.dumps(opp_data):
            opp_data['cache_status'] = "CACHE_UPDATED"
        else:
            opp_data['cache_status'] = "CACHE_NOT_UPDATED"

        return Response(opp_data)
