from asyncio import create_task
from collections import OrderedDict
from typing import Dict, Tuple

from gi.repository import Gtk, Adw

from .repository import Repository
from .ui import setup_window, setup_header_bar, setup_content, update_ui, setup_progress_dialog
from .sys import refresh_branches, apply_changes, get_installed_package_versions
from .utils import show_toast, show_results
from sys import exit


class BranchyApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.furios.Branchy')
        self.repositories: Dict[str, Repository] = OrderedDict()
        self.changed_branches: Dict[str, Tuple[str, str]] = {}
        self.enabled_branches: Dict[str, str] = {}
        self.initial_branches: Dict[str, str] = {}
        self.system_branches: Dict[str, Tuple[str, str]] = {}
        self.installed_versions: Dict[str, str] = {}

    def clear(self):
        self.repositories.clear()
        self.enabled_branches.clear()
        self.system_branches.clear()
        self.changed_branches.clear()
        self.initial_branches.clear()
        self.apply_button.set_sensitive(False)

    def do_activate(self):
        self.win = setup_window(self)
        self.win.connect('close-request', lambda _: exit(0))
        self.header_bar, self.search_entry, self.apply_button = setup_header_bar(self)
        self.content_box, self.scrolled, self.spinner = setup_content(self)

        create_task(self.refresh_branches())
        self.win.present()

    async def refresh_branches(self):
        self.show_loading_screen()
        self.clear()

        try:
            self.installed_versions = await get_installed_package_versions()
            await refresh_branches(self)
            self.update_ui()
        except Exception as e:
            self.show_results("Uh oh", f"Error refreshing branches: {str(e)}")

    def update_ui(self):
        update_ui(self)
        self.hide_loading_screen()

    def get_affected_packages(self):
        affected_packages = []
        for repo, (old_branch, new_branch) in self.changed_branches.items():
            if old_branch is None:
                old_branch = "(none)"
            if new_branch is None:
                new_branch = "(none)"

            if old_branch and new_branch and old_branch == new_branch:
                # We only allow users to enable the same branch they're already on if there's an update.
                affected_packages.append(f"• {repo}: update to latest {new_branch}")
            elif repo in self.system_branches:
                system_branch, system_file = self.system_branches[repo]

                if old_branch == system_branch:
                    old_branch = "(none)"

                affected_packages.append(f"• {repo}: {system_branch} ({system_file}) + {old_branch} → {new_branch}")
            else:
                affected_packages.append(f"• {repo}: {old_branch} → {new_branch}")

        return "\n".join(affected_packages)

    def on_apply_clicked(self, button):
        affected_packages = self.get_affected_packages()
        
        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading="Apply Branches?",
            body=f"{affected_packages}",
        )

        dialog.add_response("cancel", "Nah")
        dialog.add_response("update", "Update Lists")
        dialog.add_response("install", "Update and Install")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)

        dialog.connect('response', self.on_apply_response)
        dialog.present()

    def on_apply_response(self, dialog, response_id):
        if response_id == "update":
            create_task(self.apply_changes())
        elif response_id == "install":
            create_task(self.apply_changes(also_install=True))

    async def apply_changes(self, also_install=False):
        dialog, title, terminal, close_button = setup_progress_dialog(self, "Workin’ on it…")
        buff = terminal.get_buffer()
        dialog.present()

        def append_to_terminal(line):
            buff.insert_at_cursor(line.decode('utf-8'))
            terminal.scroll_to_mark(buff.get_insert(), 0.0, False, 0.0, 1.0)

        try:
            await apply_changes(self, output_stream_callback=append_to_terminal)
            title.set_text("Everything went well!")
            await self.refresh_branches()
        except Exception as e:
            print(e)
            title.set_text("Uh oh!")
            append_to_terminal(f"\n\nError applying changes: {str(e)}")
        finally:
            close_button.set_sensitive(True)

    def show_loading_screen(self):
        self.scrolled.set_child(self.spinner)
        self.spinner.start()

        self.content_box.set_opacity(0)

    def hide_loading_screen(self):
        self.spinner.stop()
        self.scrolled.set_child(self.content_box)

        self.content_box.set_opacity(1)

    def on_search_changed(self, search_entry):
        search_text = search_entry.get_text().lower()
        for child in self.content_box:
            self.search_recursively(child, search_text)

    def search_recursively(self, widget, search_text, force_visible=False):
        if isinstance(widget, Adw.PreferencesGroup):
            repo_title = widget.get_title().lower()
            visible_children = not search_text or search_text in repo_title
            for child in widget:
                if self.search_recursively(child, search_text, force_visible=visible_children):
                    visible_children = True
            widget.set_visible(visible_children)
            return visible_children
        elif isinstance(widget, Adw.ActionRow):
            row_visible = force_visible or not search_text or search_text in widget.get_title().lower()
            widget.set_visible(row_visible)
            return row_visible
        elif isinstance(widget, Gtk.Widget):
            visible_children = force_visible
            for child in widget:
                if self.search_recursively(child, search_text, force_visible):
                    visible_children = True
            return visible_children
        return force_visible

    def on_branch_toggled(self, radio, repo, branch_object):
        classes = ' '.join(radio.get_css_classes())
        branch = branch_object.name

        if classes and 'update-needed' in classes:
            # Packages that need updates completely bypass the usual toggling logic. This would be a lot simpler if
            # rather than having active and sensitive, we had a ternary state for the radio buttons. But GTK, good
            # API design, etc.
            if classes == 'update-needed-untouched':
                radio.set_css_classes(['update-needed-update'])
                radio.set_inconsistent(False)
                radio.set_active(True)
                self.changed_branches[repo] = (branch, branch)
                self.enabled_branches[repo] = branch
            elif classes == 'update-needed-update':
                radio.set_css_classes(['update-needed-delete'])
                radio.set_active(False)
                radio.set_inconsistent(False)
                self.changed_branches[repo] = (branch, None)
                self.enabled_branches.pop(repo, None)
            else:
                radio.set_css_classes(['update-needed-untouched'])
                radio.set_inconsistent(True)
                radio.set_active(True)
                self.changed_branches.pop(repo, None)
                self.enabled_branches[repo] = self.initial_branches.get(repo)

            self.apply_button.set_sensitive(bool(self.changed_branches))
            return

        # If this branch has an "update-needed" radio button, we need to toggle it off manually too. We can reset it to its
        # update-needed-delete state, so if the user selects it again, we go back to the original state.
        for other_branch in self.repositories[repo].branches:
            if 'update-needed' in ' '.join(other_branch.radio.get_css_classes()):
                other_branch.radio.set_css_classes(['update-needed-delete'])
                other_branch.radio.set_active(False)
                other_branch.radio.set_inconsistent(False)
                self.changed_branches[repo] = (other_branch.name, None)

        # If we are the system branch and we are already enabled, we do nothing
        if radio.get_active() and repo in self.system_branches:
            system_branch, _ = self.system_branches[repo]
            if branch == system_branch:
                return

        radio.set_active(not radio.get_active())

        if radio.get_active():
            old_branch = self.enabled_branches.get(repo)
            if old_branch != branch:
                if branch is None:
                    if repo in self.enabled_branches:
                        del self.enabled_branches[repo]
                else:
                    self.enabled_branches[repo] = branch

                initial_branch = self.initial_branches.get(repo)
                if initial_branch != branch:
                    self.changed_branches[repo] = (initial_branch, branch)
                else:
                    self.changed_branches.pop(repo, None)
        else:
            if repo in self.enabled_branches:
                del self.enabled_branches[repo]
                initial_branch = self.initial_branches.get(repo)
                if initial_branch is not None:
                    self.changed_branches[repo] = (initial_branch, None)
                else:
                    self.changed_branches.pop(repo, None)

            # Ensure the system branch is selected if it's available.
            if repo in self.system_branches:
                system_branch, _ = self.system_branches[repo]
                for other_branch in self.repositories[repo].branches:
                    if other_branch.name == system_branch:
                        other_branch.radio.set_active(True)

                        if repo in self.enabled_branches:
                            del self.enabled_branches[repo]

                        initial_branch = self.initial_branches.get(repo)
                        if initial_branch is not None:
                            self.changed_branches[repo] = (initial_branch, None)
                        else:
                            self.changed_branches.pop(repo, None)

                        break

        self.apply_button.set_sensitive(bool(self.changed_branches))

    show_toast = show_toast
    show_results = show_results
