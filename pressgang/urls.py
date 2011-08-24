from django.conf.urls.defaults import *

urlpatterns = patterns('',
	(r'^', include('pressgang.core.urls')),
	(r'^accounts/', include('pressgang.accounts.urls')),
	(r'^actions/', include('pressgang.actions.urls')),
	(r'^install/', include('pressgang.actions.install.urls')),
	(r'^lockdown/', include('pressgang.actions.lockdown.urls')),
	(r'^manage/', include('pressgang.actions.manage.urls')),
	(r'^revert/', include('pressgang.actions.revert.urls'))
)
