"""
URL configuration for tns_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import routers
from tns_api import views

router = routers.DefaultRouter()
router.register(r'allowances', views.AllowanceView, 'allowance')
router.register(r'approval-stages', views.ApprovalStageView, 'approval-stage')
router.register(r'employee', views.EmployeeView, 'employee')
router.register(r'claims', views.ClaimView, 'claims')
router.register(r'claim-lines', views.ClaimLineView, 'claim-line')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/enums/', views.enums_view, name='enums'),
]
