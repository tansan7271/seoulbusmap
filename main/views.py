from django.shortcuts import render, redirect
from django.http import *
from . import models

def index(request):
  return render(request, 'main/index.html')