from asyncio import create_task
from gi.repository import Gtk, Adw
from .utils import get_time_ago


def setup_window(app):
    win = Adw.ApplicationWindow(application=app)
    win.set_default_size(600, 600)
    win.set_title('Experiments')

    app.toolbar_view = Adw.ToolbarView()
    app.toast_overlay = Adw.ToastOverlay()
    app.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    app.toast_overlay.set_child(app.toolbar_view)
    app.toolbar_view.set_content(app.main_box)
    win.set_content(app.toast_overlay)

    return win


def setup_header_bar(app):
    header_bar = Gtk.Box(spacing=12)
    header_bar.set_css_name('box')

    adw_header_bar = Adw.HeaderBar()
    adw_header_bar.set_title_widget(header_bar)
    app.toolbar_view.add_top_bar(adw_header_bar)

    refresh_button = Gtk.Button(icon_name='view-refresh-symbolic')
    refresh_button.connect('clicked', lambda _: create_task(app.refresh_branches()))
    header_bar.append(refresh_button)

    search_entry = Gtk.SearchEntry(placeholder_text="Just type...")
    search_entry.connect('search-changed', app.on_search_changed)
    search_entry.set_hexpand(True)
    search_entry.set_halign(Gtk.Align.FILL)
    header_bar.append(search_entry)

    apply_button = Gtk.Button(label='Apply')
    apply_button.add_css_class('suggested-action')
    apply_button.connect('clicked', app.on_apply_clicked)
    apply_button.set_sensitive(False)
    header_bar.append(apply_button)

    return header_bar, search_entry, apply_button


def setup_content(app):
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    app.main_box.append(scrolled)

    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content_box.set_margin_top(24)
    content_box.set_margin_bottom(24)
    content_box.set_margin_start(24)
    content_box.set_margin_end(24)
    scrolled.set_child(content_box)

    spinner = Gtk.Spinner()
    spinner.set_size_request(32, 32)
    spinner.set_halign(Gtk.Align.CENTER)
    spinner.set_valign(Gtk.Align.CENTER)

    return content_box, scrolled, spinner


def update_ui(app):
    while True:
        child = app.content_box.get_first_child()
        if child is None:
            break
        app.content_box.remove(child)

    for repo, repository in app.repositories.items():
        repo_card = Adw.PreferencesGroup(title=repo)
        app.content_box.append(repo_card)

        radio_group = None
        for branch in repository.branches:
            row = Adw.ActionRow(title=branch.name)
            time_ago = get_time_ago(branch.timestamp)
            row.set_subtitle(f"{time_ago}")

            radio = Gtk.CheckButton()
            row.add_suffix(radio)
            radio.set_group(radio_group)

            branch.radio = radio

            if radio_group is None:
                radio_group = radio

            # Irritatingly, we can't use the radio's button toggled signal because it wouldn't allow the user to disable
            # a branch that is already enabled, nor does it play nice with our ternary state for the radio buttons. So we
            # just use a gesture to handle the toggling.
            click_controller = Gtk.GestureClick()
            click_controller.connect('released', lambda gesture, button, x, y, radio, repo, branch: app.on_branch_toggled(radio, repo, branch), radio, repo, branch)
            row.add_controller(click_controller)

            # We also have to disable clicking on the radio button, since we handle the toggling ourselves.
            # We do this by removing the default click controller. :/
            click_controller = radio.observe_controllers()[0]
            if click_controller:
                radio.remove_controller(click_controller)

            radio.set_active(app.enabled_branches.get(repo) == branch.name)

            if repo in app.system_branches:
                system_branch, system_file = app.system_branches[repo]
                if branch.name == system_branch:
                    radio.set_active(app.enabled_branches.get(repo, branch.name) == branch.name)
                    radio.set_sensitive(False)
                    row.set_subtitle(f"{row.get_subtitle()} · from {system_file}")

            if app.enabled_branches.get(repo) == branch.name and branch.version and app.installed_versions.get(repo) and branch.version != app.installed_versions[repo]:
                radio.set_inconsistent(True)
                radio.set_css_classes(['update-needed-untouched'])
                # row.set_subtitle(f"{row.get_subtitle()} · ⚠️ version mismatch ⚠️")

                warning_button = Gtk.MenuButton.new()
                warning_button.set_icon_name('dialog-warning-symbolic')
                warning_button.set_has_frame(False)

                popover = Gtk.Popover()
                info_container = Adw.Clamp()
                info_container.set_maximum_size(app.win.get_width() / 2 - 24)

                info_container.set_margin_top(6)
                info_container.set_margin_bottom(6)
                info_container.set_margin_start(6)
                info_container.set_margin_end(6)

                info_label = Gtk.Label(label=f"Installed: {app.installed_versions[repo]}\n\nAvailable: {branch.version}")
                info_label.set_wrap(True)

                info_container.set_child(info_label)
                popover.set_child(info_container)
                warning_button.set_popover(popover)

                row.add_prefix(warning_button)

            repo_card.add(row)

    app.changed_branches = {}

    # If branches got removed from the server, enabled_branches won't match initial_branches. Detect that and add them to changed_branches.
    for repo, branch in app.initial_branches.items():
        if repo not in app.enabled_branches or branch not in app.enabled_branches[repo]:
            app.changed_branches[repo] = (branch, None)

    app.apply_button.set_sensitive(not not app.changed_branches)


def setup_progress_dialog(app, title) -> tuple[Adw.Dialog, Gtk.Label, Gtk.TextView, Gtk.Button]:
    dialog = Adw.Dialog(title=title, can_close=False)
    dialog.set_content_width(app.win.get_width())
    dialog.set_content_height(app.win.get_height())

    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content_box.set_margin_top(24)
    content_box.set_margin_bottom(24)
    content_box.set_margin_start(24)
    content_box.set_margin_end(24)
    dialog.set_child(content_box)

    title_label = Gtk.Label(label=title)
    title_label.set_halign(Gtk.Align.CENTER)
    title_label.set_margin_bottom(12)
    title_label.get_style_context().add_class('title-1')
    content_box.append(title_label)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.get_style_context().add_class('view')
    content_box.append(scrolled)

    terminal = Gtk.TextView()
    terminal.set_editable(False)
    terminal.set_monospace(True)
    scrolled.set_child(terminal)

    close_button = Gtk.Button(label='Close')
    close_button.connect('clicked', lambda _: dialog.force_close())
    close_button.set_halign(Gtk.Align.CENTER)
    close_button.add_css_class('suggested-action')
    close_button.set_margin_top(12)
    close_button.set_sensitive(False)
    content_box.append(close_button)

    return dialog, title_label, terminal, close_button
