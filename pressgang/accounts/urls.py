from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('django.contrib.auth.views',
	url(r'^login/$', 'login', {'template_name': 'pressgang/accounts/login.html'}, 'login'),
	url(r'^logout/$', 'logout_then_login', name='logout')
)

urlpatterns += patterns('pressgang.accounts.views',
	url(r'^access-denied/$', 'access_denied', name='access-denied')
)
