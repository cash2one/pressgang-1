
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from pressgang.actions.lockdown.exceptions import LockdownError
from pressgang.actions.lockdown.steps import LockdownStep
from pressgang.actions.options.utils import sitewide_activate_plugin
from pressgang.core.exceptions import PressGangError
from pressgang.utils.templates import get_template_dir
from pressgang.utils.urls import url_join

import os
import re
import shutil
import tempfile

class Step(LockdownStep):

	name = _("Cache configuration")

	# The directory name of the plugin
	_PLUGIN_DIR_NAME = "wp-super-cache"

	# The path to the plugin used in activation
	_PLUGIN_WP_ID = "wp-super-cache/wp-cache.php"

	# The URL of the plugin's page, relative to the blog's admin URL
	_PLUGIN_PAGE_URL = "options-general.php?page=wpsupercache"

	# Files used by the plugin, relative to wp-content
	_PLUGIN_FILES = ['advanced-cache.php', 'wp-cache-config.php']

	# Directories used by the plugin, relative to wp-content
	_PLUGIN_DIRS = ['cache']

	# The name of the autogenerated cache dir, relative to wp-content
	_PLUGIN_CACHE_DIR = "cache"

	# The start and end lines for .htaccess cache-configuration lines
	_HTACCESS_CACHE_START = '# BEGIN WPSuperCache'
	_HTACCESS_CACHE_END = '# END WPSuperCache'

	# Lines in the configuration file added by the caching plugin
	_CONFIG_CACHE_LINES = [re.compile(r'define.+WP_CACHE')]

	# A list of Apache directives for the cache directory
	_APACHE_CACHE_DIRECTIVES = ["AllowOverride FileInfo Options"]

	def execute(self, blog, lockdown):
		"""Aggressively configure the WP Super Cache plugin."""

		# Precompute a few paths
		self._blog = blog
		self._install_path = os.path.join(self._blog.plugins_path, self._PLUGIN_DIR_NAME)
		self._cache_dir = os.path.join(self._blog.wp_content_path, self._PLUGIN_CACHE_DIR)
		self._files_path = None

		# Create a clean baseline for installing the plugin
		self.start(_("Removing old caching plugin data."))
		self._reset_config_file()
		self._reset_htaccess()
		self._delete_plugin_files()
		self.complete(_("Old plugin data removed."))

		# Install and configure the plugin only if we're locking down the blog
		if lockdown.locking:
			self.start(_("Installing and activating the caching plugin."))
			self._install_plugin()
			self.complete(_("Caching plugin installed and activated"))

			self.start(_("Configuring the caching plugin."))
			self._check_apache_conf()
			self._configure_plugin()
			self.complete(_("Caching plugin configured."))

	def _visit_plugin_admin_page(self):
		"""Visits the plugin's admin page to allow it to perform sanity checks."""
		self._blog.make_admin_request(
			url_join(self._blog.admin_page_url, self._PLUGIN_PAGE_URL))

	def _reset_config_file(self):
		"""Clears any mention of caching from the blog's config file."""

		# Search for any cache lines in the config file
		has_cache = False
		try:
			config = open(self._blog.config_file_path, 'r')
		except IOError, e:
			raise LockdownError(_("The configuration file at %(file)s could not be read.") % {'file': self._blog.config_file_path}, e)
		(temp_config_desc, temp_config_path) = tempfile.mkstemp()
		temp_config = os.fdopen(temp_config_desc, 'w')
		for config_line in config:
			is_cache_line = False
			for cache_line in self._CONFIG_CACHE_LINES:
				if cache_line.search(config_line):
					has_cache = True
					is_cache_line = True
					break
			if not is_cache_line:
				temp_config.write(config_line)
		config.close()
		temp_config.close()

		# If there are cache lines in the config file, remove them
		if has_cache:
			try:
				shutil.copyfile(temp_config_path, self._blog.config_file_path)
			except IOError, e:
				raise LockdownError(_("The configuration file at %(file)s could not be cleared of cache-related code.") % {'file': self._blog.config_file_path}, e)
			finally:
				os.remove(temp_config_path)
		else:
			os.remove(temp_config_path)

	def _reset_htaccess(self):
		"""Removes any additions by the caching plugin to the blog's .htaccess file."""

		# See if the .htaccess file contains lines generated by the cache plugin
		in_cache = False
		has_cache = False
		try:
			htaccess = open(self._blog.htaccess_path, 'r')
		except IOError, e:
			raise LockdownError(_("The .htaccess file at %(file)s could not be read.") % {'file': self._blog.htaccess_path}, e)
		(temp_htaccess_desc, temp_htaccess_path) = tempfile.mkstemp()
		temp_htaccess = os.fdopen(temp_htaccess_desc, 'w')
		for line in htaccess:
			if line.startswith(self._HTACCESS_CACHE_START):
				in_cache = True
				has_cache = True
			if not in_cache:
				temp_htaccess.write(line)
			if line.startswith(self._HTACCESS_CACHE_END):
				in_cache = False
		htaccess.close()
		temp_htaccess.close()

		# If the .htaccess file has cache lines, remove them
		if has_cache:
			try:
				shutil.copyfile(temp_htaccess_path, self._blog.htaccess_path)
			except IOError, e:
				raise LockdownError(_("The .htaccess file at %(file)s could not be cleared of cache code.") % {'file': self._blog.htaccess_path}, e)
			finally:
				os.remove(temp_htaccess_path)
		else:
			os.remove(temp_htaccess_path)

	def _delete_plugin_files(self):
		"""Removes all files associated with the caching plugin."""

		# Remove files created by the plugin
		for file in self._PLUGIN_FILES:
			file_path = os.path.join(self._blog.wp_content_path, file)
			if os.path.isfile(file_path):
				try:
					os.remove(file_path)
				except OSError, e:
					raise LockdownError(_("Unable to remove the plugin file at %(file)s.") % {'file': file_path}, e)

		# Remove directories created by the plugin
		for dir in self._PLUGIN_DIRS:
			dir_path = os.path.join(self._blog.wp_content_path, dir)
			if os.path.isdir(dir_path):
				try:
					shutil.rmtree(dir_path)
				except OSError, e:
					raise LockdownError(_("Unable to remove the plugin directory at %(dir)s.") % {'dir': dir_path}, e)

		# Clear the actual plugin file
		if os.path.isdir(self._install_path):
			try:
				shutil.rmtree(self._install_path)
			except OSError, e:
				raise LockdownError(_("Unable to remove the caching plugin at %(dir)s.") % {'dir': self._install_path}, e)

	def _install_plugin(self):
		"""Installs and activates the plugin."""

		# Copy the plugin's source to the blog
		source_dir = get_template_dir(os.path.join('pressgang/lockdown/cache', self._PLUGIN_DIR_NAME))
		if not source_dir:
			raise LockdownError(_("Unable to find the source for the WP Super Cache plugin in any of the template directories."))
		try:
			shutil.copytree(source_dir, self._install_path)
		except OSError, e:
			raise LockdownError(_("Unable to copy the plugin source from %(from)s to the blog at %(to)s.") % {'from': source_dir, 'to': self._install_path}, e)
		self._files_path = os.path.dirname(source_dir)

		# Activate the plugin on every blog on the site by first activating
		# it as a plugin and then visiting its base page
		try:
			sitewide_activate_plugin(self._PLUGIN_WP_ID, self._blog)
		except PressGangError, e:
			raise LockdownError(_("Unable to activate the caching plugin."), e)
		else:
			self._visit_plugin_admin_page()

		# Verify that the plugin activation worked, which is marked by the
		# presence of certain auto-generated files, raising an error if it didn't
		for file in self._PLUGIN_FILES:
			path = os.path.join(self._blog.wp_content_path, file)
			if not os.path.isfile(path):
				raise LockdownError(_("Plugin activation failed, as the file %(file)s could not be found.") % {'file': path})

	def _check_apache_conf(self):
		"""
		Verifies that the blog's Apache configuration file is configured
		to allow the WP Super Cache plugin to function properly.
		"""

		in_dir = False
		matched_directives = 0

		# Configure the searches for the cache directory
		start_dir_search = re.compile(r'<Directory\s+["\']%s["\'](\s+)?>' % self._cache_dir)
		end_dir_search =  re.compile(r'<\/Directory>')

		# Search for any reference to the required directives in the config file
		try:
			apache_conf = open(self._blog.apache_conf_path, 'r')
		except IOError, e:
			raise LockdownError(_("Unable to open the blog's Apache configuration file for reading at %(file)s.") % {'file': self._blog.apache_conf_path}, e)
		(temp_conf_desc, temp_conf_path) = tempfile.mkstemp()
		temp_conf = os.fdopen(temp_conf_desc, 'w')
		for line in apache_conf:
			if start_dir_search.search(line):
				in_dir = True
			if in_dir:
				for directive in self._APACHE_CACHE_DIRECTIVES:
					if directive == line.strip():
						matched_directives += 1
			else:
				temp_conf.write(line)
			if in_dir and end_dir_search.search(line):
				in_dir = False
		apache_conf.close()

		# If the config file does is not configured for the cache directory,
		# write the appropriate lines to the
		if matched_directives != len(self._APACHE_CACHE_DIRECTIVES):

			# Output the non-cache lines together with the new cache directives
			lines = ["<Directory \"%s\">" % self._cache_dir]
			lines.extend(self._APACHE_CACHE_DIRECTIVES)
			lines.append("</Directory>")
			for line in lines:
				temp_conf.write("%s\n" % line)
			temp_conf.close()

			try:
				shutil.copyfile(temp_conf_path, self._blog.apache_conf_path)
			except IOError, e:
				raise LockdownError(_("Unable to modify the blog's Apache configuration file at %(file)s to support caching.") % {'file': self._blog.apache_conf_path}, e)
			finally:
				os.remove(temp_conf_path)
		else:
			temp_conf.close()
			os.remove(temp_conf_path)

	def _configure_plugin(self):
		"""Configures the plugin after it has been installed."""

		# Copy over the custom cache config file
		cache_config = os.path.join(self._files_path, 'wp-cache-config.php')
		try:
			shutil.copy(cache_config, self._blog.wp_content_path)
		except OSError, e:
			raise LockdownError(_("Unable to copy the custom cache config file from %(from)s to %(to)s.") % {'from': cache_config, 'to': self._blog.wp_content_path}, e)

		# Copy the plugin's custom .htaccess file used on its cache directory
		origin = os.path.join(self._files_path, 'plugin.htaccess')
		destination = os.path.join(self._cache_dir, '.htaccess')
		try:
			shutil.copyfile(origin, destination)
		except OSError, e:
			raise LockdownError(_("Unable to copy the cache directory's .htaccess file from %(from)s to %(to)s") % {'from': origin, 'to': destination}, e)

		# Extend the blog's main .htaccess file with the cache plugin's lines
		try:
			blog_htaccess = open(self._blog.htaccess_path, 'r')
		except IOError, e:
			raise LockdownError(_("Unable to open the blog's .htaccess file for reading at %(file)s.") % {'file': self._blog.htaccess_path}, e)
		(temp_htaccess_desc, temp_htaccess_path) = tempfile.mkstemp()
		temp_htaccess = os.fdopen(temp_htaccess_desc, 'w')
		for line in blog_htaccess:
			temp_htaccess.write(line)
		blog_htaccess.close()
		temp_htaccess.write(render_to_string('pressgang/lockdown/cache/blog.htaccess',
			{'relative_url': self._blog.relative_url_slashes}))
		temp_htaccess.close()
		try:
			shutil.copyfile(temp_htaccess_path, self._blog.htaccess_path)
		except IOError, e:
			raise LockdownError(_("Unable to modify the blog's .htaccess for at %(file)s to support caching.") % {'file': self._blog.htaccess_path}, e)
		finally:
			os.remove(temp_htaccess_path)

		# Reload Apache and visit the plugin's admin page to seal the configuration
		self._visit_plugin_admin_page()
