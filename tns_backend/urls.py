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
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import routers
from tns_api import views

router = routers.DefaultRouter()
router.register(r'allowances', views.AllowanceView, 'allowance')
router.register(r'approval-stages', views.ApprovalStageView, 'approval-stage')
router.register(r'employee', views.EmployeeView, 'employee')
router.register(r'claims', views.ClaimView, 'claims')
router.register(r'claim-lines', views.ClaimLineView, 'claim-line')
router.register(r'receipts', views.ReceiptView, 'receipt')
router.register(r'gps-validations', views.GPSValidationView, 'gps-validation')
router.register(r'threshold-configs', views.ThresholdConfigView, 'threshold-config')
router.register(r'locations', views.LocationView, 'location')
router.register(r'cities', views.LocationView, 'city')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/openai-health/', views.openai_health_view, name='openai-health'),
    path('api/routes/driving/', views.driving_route_view, name='driving-route'),
    path('api/enums/', views.enums_view, name='enums'),
    path('api/auth/login/', views.login_view, name='login'),
    path('api/auth/signup/', views.signup_view, name='signup'),
    path('api/auth/logout/', views.logout_view, name='logout'),
    path('api/auth/me/', views.me_view, name='me'),
    path('api/auth/password-reset/', views.password_reset_view, name='password-reset'),
    path('api/users/', views.users_view, name='users'),
    path('api/users/<int:user_id>/role/', views.user_role_update_view, name='user-role-update'),
    path('api/fraud/train/', views.train_fraud_model_view, name='fraud-train'),
    path('api/fraud/train-csv/', views.train_fraud_model_csv_view, name='fraud-train-csv'),
    path('api/fraud/model/', views.fraud_model_status_view, name='fraud-model'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
