
from django.utils.translation import ugettext_lazy as _

from pressgang.actions.install.addblogs.steps import BlogAdditionStep
from pressgang.actions.install.addblogs.exceptions import BlogAdditionError
from pressgang.actions.options.exceptions import OptionsError
from pressgang.utils.apache import reload_apache

class Step(BlogAdditionStep):

	name = _("blog creation")

	def execute(self, blog, adder):
		"""Creates child blogs for the specified users."""

		# Instantiate a dummy installer to use its ability to provide usernames,
		# paths and option setting
		installer = adder.blog_type(blog=blog)

		# Create a blog for each user's email address
		for user_email in adder.users:
			self.start(_("Creating blog for user %(email)s.") % {'email': user_email})
			blog.create_blog_for_user(
				installer.provide_username(user_email),
				user_email,
				installer.provide_user_blog_slug(user_email),
				installer.provide_child_blog_title(user_email))
			self.complete(_("User added."))

		# Apply the chosen blog type's options to the child blogs
		self.start(_("Applying global customizations."))
		try:
			installer.options.all_blogs.apply(blog)
		except OptionsError, e:
			raise BlogAdditionError(_("Global customizations could not be applied."), e)
		self.complete(_("Global customizations applied."))
		self.start(_("Applying child-blog customizations."))
		try:
			installer.options.child_blogs.apply(blog)
		except OptionsError, e:
			raise BlogAdditionError(_("Child-blog customizations could not be applied."), e)
		self.complete(_("Child-blog customizations applied."))

		# Restart Apache in the end to ensure a clean install
		self.start(_("Reloading Apache."))
		reload_apache()
		self.complete(_("Apache successfully reloaded."))