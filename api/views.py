from django.shortcuts import render
from django.http import HttpResponse
from django.http import JsonResponse


def Home(request):
    return HttpResponse("heloooo")
