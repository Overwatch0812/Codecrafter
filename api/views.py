from django.shortcuts import render
from django.http import HttpResponse
from django.http import JsonResponse


def Home(request):
    return HttpResponse("heloooo")

def hit_weather(request):
    import http.client

    conn = http.client.HTTPSConnection("the-weather-api.p.rapidapi.com")

    headers = {
        'x-rapidapi-key': "42047b4750msh234436c97fc8894p1a2e84jsn3df40fb61052",
        'x-rapidapi-host': "the-weather-api.p.rapidapi.com"
    }

    conn.request("GET", "/api/weather/mumbai", headers=headers)

    res = conn.getresponse()
    data = res.read()

    return JsonResponse(data.decode("utf-8"),safe=False)
