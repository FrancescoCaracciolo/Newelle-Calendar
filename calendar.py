from gi.repository import Gio, Gtk, Adw, GObject, Pango, Gdk
from pydub.utils import json
from .utility.pip import find_module, install_module
from .extensions import NewelleExtension

from datetime import datetime, date, timedelta
from typing import Optional, List

import os
import shutil
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from dateutil import tz
import uuid
from .handlers import ExtraSettings, PromptDescription


class CalendarExtension(NewelleExtension):
    id = "calendar"
    name = "Calendar"
    calendar_manager = None
    last_operation_success = False
    last_error_message = ""
    last_search_results = []
    last_upcoming_events = []

    def __init__(self, pip_path: str, extension_path: str, settings):
        super().__init__(pip_path, extension_path, settings)
        self.caches = self.get_setting("cache", False, "{}")
        self.caches = json.loads(self.caches)

    def get_extra_settings(self) -> list:
        return super().get_extra_settings() + [
            ExtraSettings.MultilineEntrySetting("calendar_files", "iCalendar Files", "Newline separated list of iCalendar (ics) files", "~/.local/share/evolution/calendar/system/calendar.ics"),
        ]

    def save_cache(self):
        self.set_setting("cache", json.dumps(self.caches))

    def install(self):
        if not find_module("icalendar"):
            install_module("icalendar", self.pip_path)

    def get_replace_codeblocks_langs(self) -> list:
        return ["calendar", "addevent", "removeevent", "editevent", "searchevent", "events"]

    def get_additional_prompts(self) -> list:
        return [
            PromptDescription("calendar_operations", "Calendar Operations", "Perform calendar operations",
                text="- You can add an event to the calendar using:\n```addevent\nevent_name\nstart_time\nend_time\n```\n\nDate format: Use ISO format YYYY-MM-DD HH:MM (e.g., 2024-01-15 14:30)\nFor all-day events, use YYYY-MM-DD (e.g., 2024-01-15)\n\n- You can remove an event from the calendar using:\n```removeevent\nevent_name\nevent_date\n```\n\nDate format: Use ISO format YYYY-MM-DD (e.g., 2024-01-15)\nThis will remove the first event with matching name on the specified date.\n\n- You can edit an event in the calendar using:\n```editevent\noriginal_event_name\noriginal_event_date\nnew_event_name\nnew_start_time\nnew_end_time\n```\n\nDate format: Use ISO format YYYY-MM-DD HH:MM (e.g., 2024-01-15 14:30)\nFor all-day events, use YYYY-MM-DD (e.g., 2024-01-15)\nThis will find and update the first event with matching name on the specified date."
            ),
            PromptDescription("read_calendar", "Read Calendar", "Read and search calendar",
                text="- You can open the calendar using:\n```calendar\nopen\n```\n\n- You can search for events using:\n```searchevent\nevent_name\nstart_date\nend_date\n```\n\nSearch options:\n- Search by name only: ```searchevent\nevent_name```\n- Search by date only: ```searchevent\n\ndate```\n- Search by name and date: ```searchevent\nevent_name\ndate```\n- Search by date range: ```searchevent\nevent_name\nstart_date\nend_date```\n\nDate format: Use ISO format YYYY-MM-DD (e.g., 2024-01-15)\nLeave event_name empty to search all events in date range.\n\n- You can list the next 20 upcoming events using:\n```events\nlist\n```\n\nThis will show the next 20 events starting from today, sorted by date and time."
            )
        ]

    def provides_both_widget_and_answer(self, codeblock: str, lang: str) -> bool:
        if lang in ["calendar", "searchevent", "events"]:
            return True
        return False

    def get_answer(self, codeblock: str, lang: str) -> str | None:
        if lang == "addevent":
            if self.last_operation_success:
                return "Event added successfully"
            else:
                return self.last_error_message or "Error: Failed to add event"
        elif lang == "removeevent":
            if self.last_operation_success:
                return "Event removed successfully"
            else:
                return self.last_error_message or "Error: Failed to remove event"
        elif lang == "editevent":
            if self.last_operation_success:
                return "Event edited successfully"
            else:
                return self.last_error_message or "Error: Failed to edit event"
        elif lang == "searchevent":
            if self.last_error_message:
                return self.last_error_message
            return self._format_search_results(self.last_search_results)
        elif lang == "events":
            if self.last_error_message:
                return self.last_error_message
            return self._format_upcoming_events(self.last_upcoming_events)
        elif lang == "calendar":
            return "Calendar opened successfully"
        return None

    def restore_gtk_widget(self, codeblock: str, lang: str, msg_uuid=None) -> Gtk.Widget | None:
        if msg_uuid and msg_uuid in self.caches:
            cache_data = self.caches[msg_uuid]
            widget_type = cache_data.get("type")
            
            if widget_type == "calendar_button":
                if "event" in cache_data:
                    # Restore CalendarButton with event
                    event = Event.from_dict(cache_data["event"])
                    show_date = cache_data.get("show_date", True)
                    button = CalendarButton(event=event, show_date=show_date)
                    button.connect("clicked", lambda btn: self._on_event_button_clicked(event))
                    return button
                else:
                    # Restore regular calendar button
                    label = cache_data.get("label", "Open Calendar")
                    button = Gtk.Button(label=label)
                    button.connect("clicked", self.open_calendar)
                    return button
                    
            elif widget_type == "error_button":
                label = cache_data.get("label", "Error")
                error_btn = Gtk.Button(label=label)
                error_btn.set_sensitive(False)
                return error_btn
                
            elif widget_type == "success_button":
                label = cache_data.get("label", "Success")
                success_btn = Gtk.Button(label=label)
                success_btn.add_css_class("success")
                success_btn.set_sensitive(False)
                return success_btn
                
            elif widget_type == "search_results":
                # Restore search results widget
                event_dicts = cache_data.get("events", [])
                events = [Event.from_dict(event_dict) for event_dict in event_dicts]
                event_name = cache_data.get("event_name", "")
                start_date_str = cache_data.get("start_date_str", "")
                end_date_str = cache_data.get("end_date_str", "")
                return self._create_search_results_widget(events, event_name, start_date_str, end_date_str)
                
            elif widget_type == "upcoming_events":
                # Restore upcoming events widget
                event_dicts = cache_data.get("events", [])
                events = [Event.from_dict(event_dict) for event_dict in event_dicts]
                return self._create_upcoming_events_widget(events)
        
        # Fallback to parent implementation
        return super().restore_gtk_widget(codeblock, lang, msg_uuid)

    def get_gtk_widget(self, codeblock: str, lang: str, msg_uuid=None) -> Gtk.Widget | None:
        self.last_operation_success = False
        self.last_error_message = ""

        def create_error_button(message):
            self.last_error_message = message
            error_btn = Gtk.Button(label=f"Error: {message}")
            error_btn.set_sensitive(False)
            self.caches[msg_uuid] = {
                "type": "error_button",
                "label": f"Error: {message}"
            }
            self.save_cache()
            return error_btn

        def parse_event_details(lines, expected_length):
            if len(lines) < expected_length:
                return None, create_error_button("Missing information")
            return lines[:expected_length], None

        def create_event_button(event):
            button = CalendarButton(event=event, show_date=True)
            button.connect("clicked", lambda btn: self._on_event_button_clicked(event))
            self.last_operation_success = True
            self.caches[msg_uuid] = {
                "type": "calendar_button",
                "event": event.to_dict(),
                "show_date": True
            }
            self.save_cache()
            return button

        if lang == "calendar":
            b = Gtk.Button(label="Open Calendar")
            b.connect("clicked", self.open_calendar)
            self.caches[msg_uuid] = {
                "type": "calendar_button",
                "label": "Open Calendar"
            }
            self.save_cache()
            return b

        elif lang == "addevent":
            lines = codeblock.split("\n")
            event_details, error_btn = parse_event_details(lines, 3)
            if error_btn:
                return error_btn

            event_name, start_time_str, end_time_str = map(str.strip, event_details)
            try:
                all_day = len(start_time_str) == 10 and len(end_time_str) == 10
                if all_day:
                    start_date = date.fromisoformat(start_time_str)
                    end_date = date.fromisoformat(end_time_str)
                    start_time = datetime.combine(start_date, datetime.min.time())
                    end_time = datetime.combine(end_date, datetime.min.time())
                else:
                    start_time = datetime.fromisoformat(start_time_str)
                    end_time = datetime.fromisoformat(end_time_str)

                calendar_manager = self.get_calendar_manager()
                calendar_name = calendar_manager.get_calendar_names()[0] if calendar_manager.get_calendar_names() else ""

                event = Event(
                    summary=event_name,
                    start_time=start_time,
                    end_time=end_time,
                    description="",
                    location="",
                    calendar_name=calendar_name,
                    all_day=all_day
                )

                if calendar_manager.add_event(event):
                    return create_event_button(event)
                else:
                    return create_error_button("Failed to add event to calendar")

            except (ValueError, IndexError):
                return create_error_button("Invalid date format")

        elif lang == "removeevent":
            lines = codeblock.split("\n")
            event_details, error_btn = parse_event_details(lines, 2)
            if error_btn:
                return error_btn

            event_name, event_date_str = map(str.strip, event_details)
            try:
                event_date = date.fromisoformat(event_date_str)
                calendar_manager = self.get_calendar_manager()
                events_on_date = calendar_manager.get_events_for_date(event_date)
                event_to_remove = next((event for event in events_on_date if event.summary.lower() == event_name.lower()), None)

                if event_to_remove and calendar_manager.remove_event(event_to_remove):
                    success_btn = Gtk.Button(label=f"✓ Removed '{event_name}' from {event_date_str}")
                    success_btn.add_css_class("success")
                    success_btn.set_sensitive(False)
                    self.last_operation_success = True
                    self.caches[msg_uuid] = {
                        "type": "success_button",
                        "label": f"✓ Removed '{event_name}' from {event_date_str}"
                    }
                    self.save_cache()
                    return success_btn
                else:
                    return create_error_button(f"Event '{event_name}' not found on {event_date_str}")

            except ValueError:
                return create_error_button("Invalid date format")

        elif lang == "editevent":
            lines = codeblock.split("\n")
            event_details, error_btn = parse_event_details(lines, 5)
            if error_btn:
                return error_btn

            original_name, original_date_str, new_name, new_start_time_str, new_end_time_str = map(str.strip, event_details)
            try:
                original_date = date.fromisoformat(original_date_str)
                calendar_manager = self.get_calendar_manager()
                events_on_date = calendar_manager.get_events_for_date(original_date)
                original_event = next((event for event in events_on_date if event.summary.lower() == original_name.lower()), None)

                if not original_event:
                    return create_error_button(f"Event '{original_name}' not found on {original_date_str}")

                all_day = len(new_start_time_str) == 10 and len(new_end_time_str) == 10
                if all_day:
                    start_date = date.fromisoformat(new_start_time_str)
                    end_date = date.fromisoformat(new_end_time_str)
                    new_start_time = datetime.combine(start_date, datetime.min.time())
                    new_end_time = datetime.combine(end_date, datetime.min.time())
                else:
                    new_start_time = datetime.fromisoformat(new_start_time_str)
                    new_end_time = datetime.fromisoformat(new_end_time_str)

                updated_event = Event(
                    summary=new_name,
                    start_time=new_start_time,
                    end_time=new_end_time,
                    description=original_event.description,
                    location=original_event.location,
                    calendar_name=original_event.calendar_name,
                    uid=original_event.uid,
                    all_day=all_day
                )

                if calendar_manager.edit_event(original_event, updated_event):
                    return create_event_button(updated_event)
                else:
                    return create_error_button("Failed to edit event in calendar")

            except ValueError:
                return create_error_button("Invalid date format")

        elif lang == "searchevent":
            lines = codeblock.split("\n")
            event_name = lines[0].strip() if len(lines) > 0 else ""
            start_date_str = lines[1].strip() if len(lines) > 1 else ""
            end_date_str = lines[2].strip() if len(lines) > 2 else ""

            try:
                calendar_manager = self.get_calendar_manager()
                found_events = []

                if not event_name and not start_date_str:
                    return create_error_button("Please provide search criteria")

                elif event_name and not start_date_str:
                    found_events = self._search_events_by_name(calendar_manager, event_name)

                elif not event_name and start_date_str:
                    search_date = date.fromisoformat(start_date_str)
                    found_events = calendar_manager.get_events_for_date(search_date)

                elif event_name and start_date_str and not end_date_str:
                    search_date = date.fromisoformat(start_date_str)
                    events_on_date = calendar_manager.get_events_for_date(search_date)
                    found_events = [e for e in events_on_date if event_name.lower() in e.summary.lower()]

                elif start_date_str and end_date_str:
                    start_date = date.fromisoformat(start_date_str)
                    end_date = date.fromisoformat(end_date_str)
                    found_events = self._search_events_in_range(calendar_manager, start_date, end_date, event_name)

                self.last_search_results = found_events
                self.caches[msg_uuid] = {
                    "type": "search_results",
                    "events": [event.to_dict() for event in found_events],
                    "event_name": event_name,
                    "start_date_str": start_date_str,
                    "end_date_str": end_date_str
                }
                self.save_cache()

                return self._create_search_results_widget(found_events, event_name, start_date_str, end_date_str)

            except ValueError:
                return create_error_button("Invalid date format")

        elif lang == "events":
            try:
                calendar_manager = self.get_calendar_manager()
                upcoming_events = calendar_manager.get_upcoming_events(date.today(), limit=20)
                self.last_upcoming_events = upcoming_events
                self.caches[msg_uuid] = {
                    "type": "upcoming_events",
                    "events": [event.to_dict() for event in upcoming_events]
                }
                self.save_cache()

                return self._create_upcoming_events_widget(upcoming_events)

            except Exception:
                return create_error_button("Failed to load upcoming events")

    def get_calendar_manager(self):
        if self.calendar_manager is None:
            self.calendar_manager = self.refresh_calendar_manager()

        return self.calendar_manager

    def refresh_calendar_manager(self):
        calendar_files = [os.path.expanduser(path) for path in self.get_setting("calendar_files").split("\n")]
        self.calendar_manager = CalendarManager(calendar_files)
        return self.calendar_manager

    def _on_event_button_clicked(self, event):
        """Handle click on an event button - open calendar and navigate to event date."""
        calendar_manager = self.get_calendar_manager()
        calendar_widget = CalendarWidget(calendar_manager)
        
        # Set the selected date to the event's date
        event_date = event.start_time.date()
        calendar_widget.set_selected_date(event_date)
        
        tab = self.ui_controller.add_tab(calendar_widget)
        tab.set_title("Calendar")
        tab.set_icon(Gio.ThemedIcon(name="month-symbolic"))

    def _search_events_by_name(self, calendar_manager, event_name):
        """Search for events by name across all dates."""
        found_events = []
        search_term = event_name.lower()
        
        # Look through recent and upcoming events (30 days back and forward)
        start_date = date.today() - timedelta(days=30)
        end_date = date.today() + timedelta(days=30)
        
        current_date = start_date
        while current_date <= end_date:
            events_on_date = calendar_manager.get_events_for_date(current_date)
            for event in events_on_date:
                if search_term in event.summary.lower():
                    found_events.append(event)
            current_date += timedelta(days=1)
        
        # Sort by date
        found_events.sort(key=lambda e: e.start_time)
        return found_events
    
    def _search_events_in_range(self, calendar_manager, start_date, end_date, event_name=""):
        """Search for events in a date range, optionally filtered by name."""
        found_events = []
        search_term = event_name.lower() if event_name else ""
        
        current_date = start_date
        while current_date <= end_date:
            events_on_date = calendar_manager.get_events_for_date(current_date)
            for event in events_on_date:
                if not search_term or search_term in event.summary.lower():
                    found_events.append(event)
            current_date += timedelta(days=1)
        
        # Sort by date
        found_events.sort(key=lambda e: e.start_time)
        return found_events
    
    def _create_search_results_widget(self, events, event_name, start_date_str, end_date_str):
        """Create a widget displaying search results."""
        # Create main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)
        
        # Create search summary
        search_info = []
        if event_name:
            search_info.append(f"Name: '{event_name}'")
        if start_date_str and end_date_str:
            search_info.append(f"Date range: {start_date_str} to {end_date_str}")
        elif start_date_str:
            search_info.append(f"Date: {start_date_str}")
        
        summary_text = "Search: " + ", ".join(search_info) if search_info else "Search results"
        summary_label = Gtk.Label(label=summary_text)
        summary_label.add_css_class("heading")
        summary_label.set_halign(Gtk.Align.START)
        main_box.append(summary_label)
        
        # Results count
        count_label = Gtk.Label(label=f"Found {len(events)} event{'s' if len(events) != 1 else ''}")
        count_label.add_css_class("dim-label")
        count_label.set_halign(Gtk.Align.START)
        main_box.append(count_label)
        
        if events:
            # Create scrolled window for results
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_min_content_height(200)
            scrolled.set_max_content_height(400)
            
            # Create list box for events
            events_list = Gtk.ListBox()
            events_list.add_css_class("boxed-list")
            
            # Add each event as a CalendarButton
            for event in events[:10]:  # Limit to 10 results to avoid overwhelming
                button = CalendarButton(event=event, show_date=True)
                button.connect("clicked", lambda btn, e=event: self._on_event_button_clicked(e))
                
                # Create a list box row to contain the button
                row = Gtk.ListBoxRow()
                row.set_child(button)
                row.set_selectable(False)
                row.set_activatable(False)
                events_list.append(row)
            
            scrolled.set_child(events_list)
            main_box.append(scrolled)
            
            # Show truncation message if more than 10 results
            if len(events) > 10:
                truncate_label = Gtk.Label(label=f"Showing first 10 of {len(events)} results")
                truncate_label.add_css_class("dim-label")
                truncate_label.add_css_class("caption")
                truncate_label.set_halign(Gtk.Align.START)
                main_box.append(truncate_label)
        else:
            # No results found
            no_results = Gtk.Label(label="No events found matching your search criteria")
            no_results.add_css_class("dim-label")
            no_results.set_margin_top(20)
            no_results.set_margin_bottom(20)
            main_box.append(no_results)
        
        # Add "Open Calendar" button
        open_calendar_btn = Gtk.Button(label="Open Calendar")
        open_calendar_btn.add_css_class("suggested-action")
        open_calendar_btn.connect("clicked", self.open_calendar)
        open_calendar_btn.set_halign(Gtk.Align.CENTER)
        open_calendar_btn.set_margin_top(12)
        main_box.append(open_calendar_btn)
        
        return main_box

    def _format_search_results(self, events):
        """Format search results as text for the get_answer method."""
        if not events:
            return "No events found matching your search criteria."
        
        result_lines = [f"Found {len(events)} event{'s' if len(events) != 1 else ''}:"]
        result_lines.append("")  # Empty line for spacing
        
        for event in events[:10]:  # Limit to 10 for text output
            # Format event info
            event_info = []
            
            # Event name
            event_info.append(f"• {event.summary}")
            
            # Date and time
            event_date = event.start_time.date()
            today = date.today()
            
            if event_date == today:
                date_str = "Today"
            elif event_date == today + timedelta(days=1):
                date_str = "Tomorrow"
            elif event_date == today - timedelta(days=1):
                date_str = "Yesterday"
            else:
                date_str = event_date.strftime("%A, %B %d, %Y")
            
            if event.all_day:
                time_str = f"{date_str} (All day)"
            else:
                time_str = f"{date_str} at {event.start_time.strftime('%H:%M')}"
                if event.end_time:
                    time_str += f" - {event.end_time.strftime('%H:%M')}"
            
            event_info.append(f"  {time_str}")
            
            # Location if available
            if event.location:
                event_info.append(f"  📍 {event.location}")
            
            # Calendar name
            if event.calendar_name:
                event_info.append(f"  📅 {event.calendar_name}")
            
            result_lines.extend(event_info)
            result_lines.append("")  # Empty line between events
        
        if len(events) > 10:
            result_lines.append(f"... and {len(events) - 10} more event{'s' if len(events) - 10 != 1 else ''}")
        
        return "\n".join(result_lines)

    def _format_upcoming_events(self, events):
        """Format upcoming events as text for the get_answer method."""
        if not events:
            return "No upcoming events found."
        
        result_lines = [f"Next {len(events)} upcoming event{'s' if len(events) != 1 else ''}:"]
        result_lines.append("")  # Empty line for spacing
        
        current_date = None
        for event in events:
            event_date = event.start_time.date()
            
            # Add date header if date changed
            if current_date != event_date:
                today = date.today()
                if event_date == today:
                    date_header = "📅 Today"
                elif event_date == today + timedelta(days=1):
                    date_header = "📅 Tomorrow"
                elif event_date == today - timedelta(days=1):
                    date_header = "📅 Yesterday"
                else:
                    date_header = f"📅 {event_date.strftime('%A, %B %d, %Y')}"
                
                result_lines.append(date_header)
                current_date = event_date
            
            # Format event
            if event.all_day:
                time_str = "All day"
            else:
                time_str = event.start_time.strftime('%H:%M')
                if event.end_time:
                    time_str += f" - {event.end_time.strftime('%H:%M')}"
            
            event_line = f"  • {event.summary} ({time_str})"
            
            # Add location if available
            if event.location:
                event_line += f" at {event.location}"
            
            result_lines.append(event_line)
        
        return "\n".join(result_lines)

    def open_calendar(self, button):    
        calendar_manager = self.get_calendar_manager()
        calendar_manager = self.get_calendar_manager()
        calendar_widget = CalendarWidget(calendar_manager)

        tab = self.ui_controller.add_tab(calendar_widget)
        tab.set_title("Calendar")

    def _create_upcoming_events_widget(self, events):
        """Create a widget displaying upcoming events."""
        # Create main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)
        
        # Create header
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        # Upcoming events title with icon
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("view-calendar-upcoming-symbolic")
        icon.set_icon_size(Gtk.IconSize.NORMAL)
        title_box.append(icon)
        
        title_label = Gtk.Label(label="Upcoming Events")
        title_label.add_css_class("heading")
        title_label.set_halign(Gtk.Align.START)
        title_box.append(title_label)
        
        header_box.append(title_box)
        main_box.append(header_box)
        
        # Events count
        count_label = Gtk.Label(label=f"Next {len(events)} event{'s' if len(events) != 1 else ''}")
        count_label.add_css_class("dim-label")
        count_label.set_halign(Gtk.Align.START)
        main_box.append(count_label)
        
        if events:
            # Create scrolled window for events
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_min_content_height(200)
            scrolled.set_max_content_height(500)
            
            # Create list box for events
            events_list = Gtk.ListBox()
            events_list.add_css_class("boxed-list")
            
            # Group events by date for better organization
            current_date = None
            for i, event in enumerate(events):
                event_date = event.start_time.date()
                
                # Add date separator if date changed
                if current_date != event_date:
                    if i > 0:  # Add some spacing before new date (except for first)
                        separator = Gtk.Separator()
                        separator.set_margin_top(8)
                        separator.set_margin_bottom(8)
                        events_list.append(separator)
                    
                    # Add date header
                    date_row = Gtk.ListBoxRow()
                    date_row.set_selectable(False)
                    date_row.set_activatable(False)
                    
                    # Format date nicely
                    today = date.today()
                    if event_date == today:
                        date_text = "Today"
                    elif event_date == today + timedelta(days=1):
                        date_text = "Tomorrow"
                    elif event_date == today - timedelta(days=1):
                        date_text = "Yesterday"
                    else:
                        # Show day of week and date
                        date_text = event_date.strftime("%A, %B %d")
                    
                    date_label = Gtk.Label(label=date_text)
                    date_label.add_css_class("caption-heading")
                    date_label.add_css_class("accent")
                    date_label.set_halign(Gtk.Align.START)
                    date_label.set_margin_start(12)
                    date_label.set_margin_end(12)
                    date_label.set_margin_top(8)
                    date_label.set_margin_bottom(4)
                    date_row.set_child(date_label)
                    events_list.append(date_row)
                    
                    current_date = event_date
                
                # Add event button
                button = CalendarButton(event=event, show_date=False)  # Don't show date since we have headers
                button.connect("clicked", lambda btn, e=event: self._on_event_button_clicked(e))
                
                # Create a list box row to contain the button
                row = Gtk.ListBoxRow()
                row.set_child(button)
                row.set_selectable(False)
                row.set_activatable(False)
                events_list.append(row)
            
            scrolled.set_child(events_list)
            main_box.append(scrolled)
        else:
            # No upcoming events
            no_events = Gtk.Label(label="No upcoming events found")
            no_events.add_css_class("dim-label")
            no_events.set_margin_top(20)
            no_events.set_margin_bottom(20)
            main_box.append(no_events)
        
        # Add "Open Calendar" button
        open_calendar_btn = Gtk.Button(label="Open Full Calendar")
        open_calendar_btn.add_css_class("suggested-action")
        open_calendar_btn.connect("clicked", self.open_calendar)
        open_calendar_btn.set_halign(Gtk.Align.CENTER)
        open_calendar_btn.set_margin_top(12)
        main_box.append(open_calendar_btn)
        
        return main_box

class Event:
    """Represents a calendar event."""
    
    def __init__(self, summary: str, start_time: datetime, end_time: datetime, 
                 description: str = "", location: str = "", calendar_name: str = "",
                 uid: str = None, all_day: bool = False):
        self.summary = summary
        self.start_time = start_time
        self.end_time = end_time
        self.description = description
        self.location = location
        self.calendar_name = calendar_name
        self.uid = uid or str(uuid.uuid4())
        self.all_day = all_day
    
    def __str__(self):
        if self.all_day:
            return f"{self.summary}"
        return f"{self.start_time.strftime('%H:%M')} - {self.summary}"
    
    def to_dict(self):
        """Convert event to dictionary for serialization."""
        return {
            'summary': self.summary,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'description': self.description,
            'location': self.location,
            'calendar_name': self.calendar_name,
            'uid': self.uid,
            'all_day': self.all_day
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create event from dictionary."""
        return cls(
            summary=data['summary'],
            start_time=datetime.fromisoformat(data['start_time']),
            end_time=datetime.fromisoformat(data['end_time']),
            description=data.get('description', ''),
            location=data.get('location', ''),
            calendar_name=data.get('calendar_name', ''),
            uid=data.get('uid'),
            all_day=data.get('all_day', False)
        )

class CalendarManager:
    """Manages multiple iCal calendars and their events."""
    
    def __init__(self, calendar_files: List[str] = None):
        """
        Initialize CalendarManager with a list of iCal file paths.
        
        Args:
            calendar_files: List of paths to iCal files
        """
        self.calendar_files = calendar_files or []
        self.calendars = {}  # Dict[str, Calendar]
        self.events = {}     # Dict[date, List[Event]]
        self.calendar_colors = {}  # Dict[str, str] - Calendar name to color
        self._load_calendars()
    
    def _load_calendars(self):
        from icalendar import Calendar, Event as ICalEvent
        """Load all iCal files and extract events."""
        self.events.clear()
        self.calendars.clear()
        
        colors = ['#3584e4', '#33d17a', '#f6d32d', '#ff7800', '#e01b24', '#9141ac']
        color_index = 0
        
        for file_path in self.calendar_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as f:
                        cal = Calendar.from_ical(f.read())
                        
                    # Get calendar name
                    cal_name = str(cal.get('X-WR-CALNAME', os.path.basename(file_path)))
                    self.calendars[cal_name] = cal
                    
                    # Assign color
                    self.calendar_colors[cal_name] = colors[color_index % len(colors)]
                    color_index += 1
                    
                    # Extract events
                    self._extract_events_from_calendar(cal, cal_name)
                    
                except Exception as e:
                    print(f"Error loading calendar {file_path}: {e}")
    
    def _extract_events_from_calendar(self, calendar, calendar_name: str):
        """Extract events from a calendar and organize by date."""
        for component in calendar.walk():
            if component.name == "VEVENT":
                try:
                    event = self._parse_ical_event(component, calendar_name)
                    if event:
                        event_date = event.start_time.date()
                        if event_date not in self.events:
                            self.events[event_date] = []
                        self.events[event_date].append(event)
                except Exception as e:
                    print(f"Error parsing event: {e}")
    
    def _parse_ical_event(self, component, calendar_name: str) -> Optional[Event]:
        """Parse an iCal event component into an Event object."""
        try:
            summary = str(component.get('summary', 'Untitled Event'))
            
            # Handle start time
            dtstart = component.get('dtstart')
            if dtstart is None:
                return None
            
            start_dt = dtstart.dt
            all_day = isinstance(start_dt, date) and not isinstance(start_dt, datetime)
            
            if all_day:
                # All-day event
                start_time = datetime.combine(start_dt, datetime.min.time())
                end_dt = component.get('dtend')
                if end_dt:
                    end_time = datetime.combine(end_dt.dt, datetime.min.time())
                else:
                    end_time = start_time + timedelta(days=1)
            else:
                # Timed event
                if start_dt.tzinfo is None:
                    start_time = start_dt.replace(tzinfo=tz.tzlocal())
                else:
                    start_time = start_dt
                
                end_dt = component.get('dtend')
                if end_dt:
                    end_time = end_dt.dt
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=tz.tzlocal())
                else:
                    # Default to 1 hour duration
                    end_time = start_time + timedelta(hours=1)
            
            description = str(component.get('description', ''))
            location = str(component.get('location', ''))
            uid = str(component.get('uid', ''))
            
            return Event(
                summary=summary,
                start_time=start_time,
                end_time=end_time,
                description=description,
                location=location,
                calendar_name=calendar_name,
                uid=uid,
                all_day=all_day
            )
        except Exception as e:
            print(f"Error parsing event component: {e}")
            return None
    
    def get_events_for_date(self, target_date: date) -> List[Event]:
        """Get all events for a specific date, sorted by time."""
        events = self.events.get(target_date, [])
        
        # Normalize timezones before sorting to avoid comparison errors
        for event in events:
            if event.start_time.tzinfo is None:
                event.start_time = event.start_time.replace(tzinfo=tz.tzlocal())
            if event.end_time.tzinfo is None:
                event.end_time = event.end_time.replace(tzinfo=tz.tzlocal())
        
        return sorted(events, key=lambda e: (e.all_day, e.start_time))
    
    def get_upcoming_events(self, from_date: date, limit: int = 5) -> List[Event]:
        """Get upcoming events starting from a specific date."""
        upcoming = []
        current_date = from_date
        max_days = 30  # Look ahead maximum 30 days
        
        for _ in range(max_days):
            if len(upcoming) >= limit:
                break
            
            day_events = self.get_events_for_date(current_date)
            for event in day_events:
                if len(upcoming) >= limit:
                    break
                upcoming.append(event)
            
            current_date += timedelta(days=1)
        
        return upcoming[:limit]
    
    def add_event(self, event: Event) -> bool:
        """Add a new event to the appropriate calendar."""
        try:
            event_date = event.start_time.date()
            if event_date not in self.events:
                self.events[event_date] = []
            
            self.events[event_date].append(event)
            
            # Find the calendar to add to (use first calendar if calendar_name not found)
            calendar_name = event.calendar_name
            if calendar_name not in self.calendars and self.calendars:
                calendar_name = list(self.calendars.keys())[0]
                event.calendar_name = calendar_name
            
            # Write event to iCal file
            if calendar_name in self.calendars:
                self._write_event_to_calendar(event, calendar_name)
            
            return True
        except Exception as e:
            print(f"Error adding event: {e}")
            return False
    
    def edit_event(self, old_event: Event, new_event: Event) -> bool:
        """Edit an existing event."""
        try:
            # Remove old event from memory and file
            if self._remove_event_from_calendar(old_event):
                # Add new event to memory and file
                return self.add_event(new_event)
            return False
        except Exception as e:
            print(f"Error editing event: {e}")
            return False
    
    def remove_event(self, event: Event) -> bool:
        """Remove an event."""
        try:
            # Remove from memory
            event_date = event.start_time.date()
            if event_date in self.events:
                events_list = self.events[event_date]
                # Find and remove the event by UID
                for i, e in enumerate(events_list):
                    if e.uid == event.uid:
                        events_list.pop(i)
                        if not events_list:
                            del self.events[event_date]
                        break
                else:
                    return False  # Event not found in memory
            else:
                return False  # Date not found in memory
            
            # Remove from iCal file
            return self._remove_event_from_calendar(event)
            
        except Exception as e:
            print(f"Error removing event: {e}")
            return False
    
    def _create_backup(self, file_path: str) -> bool:
        """Create a backup of the calendar file before modifying it."""
        try:
            backup_path = f"{file_path}.backup"
            shutil.copy2(file_path, backup_path)
            return True
        except Exception as e:
            print(f"Warning: Could not create backup of {file_path}: {e}")
            return False
    
    def _write_event_to_calendar(self, event: Event, calendar_name: str):
        """Write an event to the appropriate iCal file."""
        from icalendar import Calendar, Event as ICalEvent
        try:
            # Find the file path for this calendar
            calendar_file = None
            for file_path in self.calendar_files:
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        temp_cal = Calendar.from_ical(f.read())
                    temp_name = str(temp_cal.get('X-WR-CALNAME', os.path.basename(file_path)))
                    if temp_name == calendar_name:
                        calendar_file = file_path
                        break
            
            if not calendar_file:
                print(f"Could not find file for calendar: {calendar_name}")
                return
            
            # Create backup before modifying
            self._create_backup(calendar_file)
            
            # Load the calendar
            calendar = self.calendars[calendar_name]
            
            # Create iCal event
            ical_event = ICalEvent()
            ical_event.add('summary', event.summary)
            ical_event.add('uid', event.uid)
            
            # Normalize timezone for event times
            start_time = event.start_time
            end_time = event.end_time
            
            if not event.all_day:
                # Ensure timezone-aware datetimes for timed events
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=tz.tzlocal())
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=tz.tzlocal())
            
            if event.all_day:
                # All-day event - use date only
                ical_event.add('dtstart', start_time.date())
                if end_time.date() != start_time.date():
                    ical_event.add('dtend', end_time.date())
            else:
                # Timed event
                ical_event.add('dtstart', start_time)
                ical_event.add('dtend', end_time)
            
            if event.description:
                ical_event.add('description', event.description)
            if event.location:
                ical_event.add('location', event.location)
            
            # Add event to calendar
            calendar.add_component(ical_event)
            
            # Write back to file
            with open(calendar_file, 'wb') as f:
                f.write(calendar.to_ical())
            
            print(f"Added event '{event.summary}' to {calendar_file}")
            
        except Exception as e:
            print(f"Error writing event to calendar file: {e}")
    
    def _remove_event_from_calendar(self, event: Event) -> bool:
        """Remove an event from the appropriate iCal file."""
        from icalendar import Calendar, Event as ICalEvent
        try:
            # Find the file path for this calendar
            calendar_file = None
            for file_path in self.calendar_files:
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        temp_cal = Calendar.from_ical(f.read())
                    temp_name = str(temp_cal.get('X-WR-CALNAME', os.path.basename(file_path)))
                    if temp_name == event.calendar_name:
                        calendar_file = file_path
                        break
            
            if not calendar_file:
                print(f"Could not find file for calendar: {event.calendar_name}")
                return False
            
            # Create backup before modifying
            self._create_backup(calendar_file)
            
            # Load the calendar fresh from file
            with open(calendar_file, 'rb') as f:
                calendar = Calendar.from_ical(f.read())
            
            # Find and remove the event
            events_to_remove = []
            for component in calendar.walk():
                if component.name == "VEVENT":
                    component_uid = str(component.get('uid', ''))
                    if component_uid == event.uid:
                        events_to_remove.append(component)
            
            # Remove found events
            for event_component in events_to_remove:
                calendar.subcomponents.remove(event_component)
            
            # Write back to file
            with open(calendar_file, 'wb') as f:
                f.write(calendar.to_ical())
            
            # Update our in-memory calendar
            self.calendars[event.calendar_name] = calendar
            
            print(f"Removed event '{event.summary}' from {calendar_file}")
            return True
            
        except Exception as e:
            print(f"Error removing event from calendar file: {e}")
            return False
    
    def get_calendar_names(self) -> List[str]:
        """Get list of all calendar names."""
        return list(self.calendars.keys())
    
    def get_calendar_color(self, calendar_name: str) -> str:
        """Get the color associated with a calendar."""
        return self.calendar_colors.get(calendar_name, '#3584e4')
    
    def reload_calendars(self):
        """Reload all calendars from files."""
        self._load_calendars()
    
    def has_events_on_date(self, target_date: date) -> bool:
        """Check if there are any events on a specific date."""
        return target_date in self.events and len(self.events[target_date]) > 0

class CalendarButton(Gtk.Button):
    """A button widget that displays a calendar icon and event information."""
    
    def __init__(self, event: Optional[Event] = None, show_date: bool = True):
        super().__init__()
        
        self.event = event
        self.show_date = show_date
        
        # Add CSS classes for styling
        self.add_css_class("flat")
        self.add_css_class("calendar-button")
        
        # Create main horizontal box
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        main_box.set_margin_top(8)
        main_box.set_margin_bottom(8)
        
        # Calendar icon on the left
        self.icon = Gtk.Image.new_from_icon_name("month-symbolic")
        self.icon.set_icon_size(Gtk.IconSize.NORMAL)
        main_box.append(self.icon)
        
        # Event information on the right
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)
        info_box.set_halign(Gtk.Align.START)
        
        # Event title or default text
        self.title_label = Gtk.Label()
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.add_css_class("heading")
        info_box.append(self.title_label)
        
        # Event details (time, date, location)
        self.details_label = Gtk.Label()
        self.details_label.set_halign(Gtk.Align.START)
        self.details_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.details_label.add_css_class("dim-label")
        self.details_label.add_css_class("caption")
        info_box.append(self.details_label)
        
        main_box.append(info_box)
        
        self.set_child(main_box)
        
        # Update content
        self._update_content()
        
        # Add custom CSS
        self._add_css()
    
    def _add_css(self):
        """Add custom CSS styling for CalendarButton."""
        css = """
        .calendar-button {
            min-height: 56px;
            padding: 0;
            border-radius: 12px;
            transition: all 200ms ease;
        }
        .calendar-button:hover {
            background: alpha(@accent_color, 0.1);
        }
        .calendar-button:active {
            background: alpha(@accent_color, 0.2);
        }
        .calendar-button .heading {
            font-weight: bold;
        }
        .calendar-button .caption {
            font-size: 0.9em;
        }
        """
        
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def _update_content(self):
        """Update the button content based on the event."""
        if self.event:
            # Set event title
            self.title_label.set_text(self.event.summary)
            
            # Build details string
            details_parts = []
            
            # Add time information
            if self.event.all_day:
                details_parts.append("All day")
            else:
                time_str = f"{self.event.start_time.strftime('%H:%M')} - {self.event.end_time.strftime('%H:%M')}"
                details_parts.append(time_str)
            
            # Add date if show_date is True and event is not today
            if self.show_date:
                event_date = self.event.start_time.date()
                today = date.today()
                
                if event_date == today:
                    details_parts.append("Today")
                elif event_date == today + timedelta(days=1):
                    details_parts.append("Tomorrow")
                elif event_date == today - timedelta(days=1):
                    details_parts.append("Yesterday")
                else:
                    # Show relative date for nearby dates
                    delta = (event_date - today).days
                    if -7 <= delta <= 7 and delta != 0:
                        if delta > 0:
                            details_parts.append(f"In {delta} day{'s' if delta > 1 else ''}")
                        else:
                            details_parts.append(f"{abs(delta)} day{'s' if abs(delta) > 1 else ''} ago")
                    else:
                        details_parts.append(event_date.strftime('%b %d'))
            
            # Add location if available
            if self.event.location:
                details_parts.append(f"📍 {self.event.location}")
            
            # Add calendar name
            if self.event.calendar_name:
                details_parts.append(f"• {self.event.calendar_name}")
            
            self.details_label.set_text(" • ".join(details_parts))
            
            # Update icon based on event type
            if self.event.all_day:
                self.icon.set_from_icon_name("view-calendar-day-symbolic")
            else:
                self.icon.set_from_icon_name("appointment-soon-symbolic")
        
        else:
            # No event - show default content
            self.title_label.set_text("No events")
            self.details_label.set_text("Click to open calendar")
            self.icon.set_from_icon_name("x-office-calendar-symbolic")
    
    def set_event(self, event: Optional[Event]):
        """Set the event to display."""
        self.event = event
        self._update_content()
    
    def get_event(self) -> Optional[Event]:
        """Get the current event."""
        return self.event
    
    def set_show_date(self, show_date: bool):
        """Set whether to show date information."""
        self.show_date = show_date
        self._update_content()
    
    def get_show_date(self) -> bool:
        """Get whether date information is shown."""
        return self.show_date

class EventDialog(Adw.Window):
    """Dialog for adding/editing events."""
    
    def __init__(self, parent, calendar_manager: CalendarManager, 
                 selected_date: date, event: Optional[Event] = None):
        super().__init__()
        self.calendar_manager = calendar_manager
        self.selected_date = selected_date
        self.event = event
        self.result = None
        
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 500)
        self.set_title("Add Event" if event is None else "Edit Event")
        
        self._build_ui()
        
        if event:
            self._populate_fields()
    
    def _build_ui(self):
        """Build the dialog user interface."""
        # Main content box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Header bar
        header = Adw.HeaderBar()
        
        # Cancel button
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        header.pack_start(cancel_btn)
        
        # Save button
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)
        header.pack_end(save_btn)
        
        main_box.append(header)
        
        # Main content
        content = Adw.PreferencesPage()
        
        # Basic info group
        basic_group = Adw.PreferencesGroup()
        basic_group.set_title("Event Details")
        
        # Title entry
        self.title_row = Adw.EntryRow()
        self.title_row.set_title("Title")
        basic_group.add(self.title_row)
        
        # Date/time group  
        datetime_group = Adw.PreferencesGroup()
        datetime_group.set_title("Date and Time")
        
        # All-day switch
        self.all_day_row = Adw.SwitchRow()
        self.all_day_row.set_title("All Day")
        self.all_day_row.connect("notify::active", self._on_all_day_toggled)
        datetime_group.add(self.all_day_row)
        
        # Start time
        self.start_time_row = Adw.ActionRow()
        self.start_time_row.set_title("Start Time")
        
        start_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.start_hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.start_hour_spin.set_value(9)  # Default to 9 AM
        self.start_minute_spin = Gtk.SpinButton.new_with_range(0, 59, 15)
        self.start_minute_spin.set_value(0)
        
        start_box.append(self.start_hour_spin)
        start_box.append(Gtk.Label(label=":"))
        start_box.append(self.start_minute_spin)
        
        self.start_time_row.add_suffix(start_box)
        datetime_group.add(self.start_time_row)
        
        # End time
        self.end_time_row = Adw.ActionRow()
        self.end_time_row.set_title("End Time")
        
        end_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.end_hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.end_hour_spin.set_value(10)  # Default to 10 AM
        self.end_minute_spin = Gtk.SpinButton.new_with_range(0, 59, 15)
        self.end_minute_spin.set_value(0)
        
        end_box.append(self.end_hour_spin)
        end_box.append(Gtk.Label(label=":"))
        end_box.append(self.end_minute_spin)
        
        self.end_time_row.add_suffix(end_box)
        datetime_group.add(self.end_time_row)
        
        # Calendar selection
        calendar_group = Adw.PreferencesGroup()
        calendar_group.set_title("Calendar")
        
        self.calendar_row = Adw.ComboRow()
        self.calendar_row.set_title("Calendar")
        
        # Populate calendar list
        calendar_model = Gtk.StringList()
        for cal_name in self.calendar_manager.get_calendar_names():
            calendar_model.append(cal_name)
        
        self.calendar_row.set_model(calendar_model)
        if calendar_model.get_n_items() > 0:
            self.calendar_row.set_selected(0)
        
        calendar_group.add(self.calendar_row)
        
        # Additional details group
        details_group = Adw.PreferencesGroup()
        details_group.set_title("Additional Details")
        
        # Location
        self.location_row = Adw.EntryRow()
        self.location_row.set_title("Location")
        details_group.add(self.location_row)
        
        # Description
        self.description_row = Adw.EntryRow()
        self.description_row.set_title("Description")
        details_group.add(self.description_row)
        
        # Add groups to content
        content.add(basic_group)
        content.add(datetime_group)
        content.add(calendar_group)
        content.add(details_group)
        
        main_box.append(content)
        
        self.set_content(main_box)
    
    def _populate_fields(self):
        """Populate fields when editing an existing event."""
        if not self.event:
            return
        
        self.title_row.set_text(self.event.summary)
        self.location_row.set_text(self.event.location)
        self.description_row.set_text(self.event.description)
        
        self.all_day_row.set_active(self.event.all_day)
        
        if not self.event.all_day:
            self.start_hour_spin.set_value(self.event.start_time.hour)
            self.start_minute_spin.set_value(self.event.start_time.minute)
            self.end_hour_spin.set_value(self.event.end_time.hour)
            self.end_minute_spin.set_value(self.event.end_time.minute)
        
        # Set calendar selection
        calendar_names = self.calendar_manager.get_calendar_names()
        if self.event.calendar_name in calendar_names:
            self.calendar_row.set_selected(calendar_names.index(self.event.calendar_name))
    
    def _on_all_day_toggled(self, switch, param):
        """Handle all-day toggle."""
        is_all_day = switch.get_active()
        self.start_time_row.set_sensitive(not is_all_day)
        self.end_time_row.set_sensitive(not is_all_day)
    
    def _on_save_clicked(self, button):
        """Handle save button click."""
        title = self.title_row.get_text().strip()
        if not title:
            return  # TODO: Show error dialog
        
        # Get selected calendar
        calendar_names = self.calendar_manager.get_calendar_names()
        selected_idx = self.calendar_row.get_selected()
        calendar_name = calendar_names[selected_idx] if calendar_names else ""
        
        # Build datetime
        if self.all_day_row.get_active():
            start_time = datetime.combine(self.selected_date, datetime.min.time())
            end_time = start_time + timedelta(days=1)
            all_day = True
        else:
            start_hour = int(self.start_hour_spin.get_value())
            start_minute = int(self.start_minute_spin.get_value())
            end_hour = int(self.end_hour_spin.get_value())
            end_minute = int(self.end_minute_spin.get_value())
            
            start_time = datetime.combine(self.selected_date, 
                                        datetime.min.time().replace(hour=start_hour, minute=start_minute))
            end_time = datetime.combine(self.selected_date,
                                      datetime.min.time().replace(hour=end_hour, minute=end_minute))
            all_day = False
        
        # Create event
        new_event = Event(
            summary=title,
            start_time=start_time,
            end_time=end_time,
            description=self.description_row.get_text(),
            location=self.location_row.get_text(),
            calendar_name=calendar_name,
            all_day=all_day,
            uid=self.event.uid if self.event else None
        )
        
        self.result = new_event
        self.close()


class CalendarWidget(Gtk.Box):
    """Modern GTK4 Adwaita Calendar Widget with event management."""
    
    # Signals
    __gsignals__ = {
        'date-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'event-added': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'event-edited': (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        'event-removed': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }
    
    def __init__(self, calendar_manager: CalendarManager):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.calendar_manager = calendar_manager
        self.selected_date = date.today()
        self.current_month = date.today().replace(day=1)
        
        # Set fixed width
        self.set_size_request(420, -1)
        
        self._build_ui()
        self._update_calendar()
        self._update_events()
    
    def _build_ui(self):
        """Build the calendar widget user interface."""
        # Header with month navigation
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        
        # Previous month button
        prev_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        prev_btn.add_css_class("flat")
        prev_btn.connect("clicked", self._on_prev_month)
        header.pack_start(prev_btn)
        
        # Next month button
        next_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        next_btn.add_css_class("flat")
        next_btn.connect("clicked", self._on_next_month)
        header.pack_end(next_btn)
        
        # Month/year title
        self.month_label = Gtk.Label()
        self.month_label.add_css_class("title-2")
        header.set_title_widget(self.month_label)
        
        self.append(header)
        
        # Calendar grid container
        calendar_frame = Gtk.Frame()
        calendar_frame.set_margin_start(12)
        calendar_frame.set_margin_end(12)
        calendar_frame.set_margin_bottom(12)
        
        calendar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Day headers
        headers_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        headers_box.set_homogeneous(True)
        headers_box.add_css_class("calendar-headers")
        
        for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            label = Gtk.Label(label=day_name)
            label.add_css_class("dim-label")
            label.set_margin_top(8)
            label.set_margin_bottom(8)
            headers_box.append(label)
        
        calendar_box.append(headers_box)
        
        # Calendar grid
        self.calendar_grid = Gtk.Grid()
        self.calendar_grid.set_row_homogeneous(True)
        self.calendar_grid.set_column_homogeneous(True)
        
        # Create day buttons (6 weeks × 7 days)
        self.day_buttons = []
        for week in range(6):
            week_buttons = []
            for day in range(7):
                btn = Gtk.Button()
                btn.set_size_request(50, 40)
                btn.add_css_class("calendar-day")
                btn.add_css_class("flat")
                btn.add_css_class("circular")
                btn.connect("clicked", self._on_day_clicked)
                self.calendar_grid.attach(btn, day, week, 1, 1)
                week_buttons.append(btn)
            self.day_buttons.append(week_buttons)
        
        calendar_box.append(self.calendar_grid)
        calendar_frame.set_child(calendar_box)
        self.append(calendar_frame)
        
        # Events section
        events_frame = Gtk.Frame()
        events_frame.set_margin_start(12)
        events_frame.set_margin_end(12)
        events_frame.set_margin_bottom(12)
        
        events_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Events header with add button
        events_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        events_header.set_margin_start(12)
        events_header.set_margin_end(12)
        events_header.set_margin_top(12)
        events_header.set_margin_bottom(6)
        
        self.events_title = Gtk.Label()
        self.events_title.set_markup("<b>Events</b>")
        self.events_title.set_halign(Gtk.Align.START)
        events_header.append(self.events_title)
        
        # Add event button
        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_btn.add_css_class("flat")
        add_btn.connect("clicked", self._on_add_event)
        events_header.append(add_btn)
        
        events_box.append(events_header)
        
        # Events scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(200)
        scrolled.set_max_content_height(300)
        
        # Events list
        self.events_list = Gtk.ListBox()
        self.events_list.add_css_class("boxed-list")
        self.events_list.set_margin_start(12)
        self.events_list.set_margin_end(12)
        self.events_list.set_margin_bottom(12)
        
        scrolled.set_child(self.events_list)
        events_box.append(scrolled)
        
        events_frame.set_child(events_box)
        self.append(events_frame)
        
        # Add custom CSS
        self._add_css()
    
    def _add_css(self):
        """Add custom CSS styling."""
        css = """
        .calendar-day {
            margin: 2px;
        }
        .calendar-day.today {
            background: @accent_color;
            color: white;
        }
        .calendar-day.selected {
            background: alpha(@accent_color, 0.3);
            border: 2px solid @accent_color;
        }
        .calendar-day.has-events {
            font-weight: bold;
        }
        .calendar-day.other-month {
            opacity: 0.5;
        }
        .calendar-headers {
            border-bottom: 1px solid @borders;
        }
        .event-row {
            padding: 8px;
        }
        .event-time {
            color: @accent_color;
            font-weight: bold;
        }
        .event-calendar {
            opacity: 0.7;
            font-size: 0.9em;
        }
        .upcoming-events-label {
            font-style: italic;
            opacity: 0.8;
            margin-top: 8px;
            margin-bottom: 4px;
        }
        .event-buttons button {
            min-width: 32px;
            min-height: 32px;
        }
        """
        
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def _update_calendar(self):
        """Update the calendar grid display."""
        # Update month label
        self.month_label.set_text(self.current_month.strftime("%B %Y"))
        
        # Calculate first day of month and number of days
        first_day = self.current_month
        last_day = (first_day.replace(month=first_day.month + 1) - timedelta(days=1)
                   if first_day.month < 12 
                   else first_day.replace(year=first_day.year + 1, month=1) - timedelta(days=1))
        
        # Get first Monday of the calendar view
        start_date = first_day - timedelta(days=first_day.weekday())
        
        # Update day buttons
        current_date = start_date
        today = date.today()
        
        for week_buttons in self.day_buttons:
            for btn in week_buttons:
                btn.set_label(str(current_date.day))
                
                # Clear previous classes
                btn.remove_css_class("today")
                btn.remove_css_class("selected")
                btn.remove_css_class("has-events")
                btn.remove_css_class("other-month")
                
                # Set button data
                btn.set_name(current_date.isoformat())
                
                # Add appropriate classes
                if current_date == today:
                    btn.add_css_class("today")
                
                if current_date == self.selected_date:
                    btn.add_css_class("selected")
                
                if current_date.month != self.current_month.month:
                    btn.add_css_class("other-month")
                
                if self.calendar_manager.has_events_on_date(current_date):
                    btn.add_css_class("has-events")
                
                current_date += timedelta(days=1)
    
    def _update_events(self):
        """Update the events list for the selected date."""
        # Clear existing events
        while True:
            child = self.events_list.get_first_child()
            if child is None:
                break
            self.events_list.remove(child)
        
        # Update events title
        self.events_title.set_markup(
            f"<b>Events - {self.selected_date.strftime('%B %d, %Y')}</b>"
        )
        
        # Get events for selected date
        today_events = self.calendar_manager.get_events_for_date(self.selected_date)
        
        # Add today's events first
        if today_events:
            for event in today_events:
                self._add_event_row(event)
        
        # Add upcoming events if less than 5 total events
        upcoming_events = []
        if len(today_events) < 5:
            upcoming_events = self.calendar_manager.get_upcoming_events(
                self.selected_date + timedelta(days=1), 
                5 - len(today_events)
            )
        
        # Add divider and upcoming events if we have both today's events and upcoming events
        if today_events and upcoming_events:
            # Add separator
            separator = Gtk.Separator()
            separator.set_margin_top(12)
            separator.set_margin_bottom(8)
            separator.set_margin_start(12)
            separator.set_margin_end(12)
            self.events_list.append(separator)
            
            # Add "Upcoming Events" label
            upcoming_label = Gtk.Label(label="Upcoming Events")
            upcoming_label.add_css_class("upcoming-events-label")
            upcoming_label.add_css_class("dim-label")
            upcoming_label.set_halign(Gtk.Align.START)
            upcoming_label.set_margin_start(12)
            upcoming_label.set_margin_end(12)
            self.events_list.append(upcoming_label)
            
            # Add upcoming events
            for event in upcoming_events:
                self._add_event_row(event)
        
        elif upcoming_events and not today_events:
            # Only upcoming events, add them with a label
            upcoming_label = Gtk.Label(label="Upcoming Events")
            upcoming_label.add_css_class("upcoming-events-label")
            upcoming_label.add_css_class("dim-label")
            upcoming_label.set_halign(Gtk.Align.START)
            upcoming_label.set_margin_start(12)
            upcoming_label.set_margin_end(12)
            upcoming_label.set_margin_top(8)
            upcoming_label.set_margin_bottom(4)
            self.events_list.append(upcoming_label)
            
            for event in upcoming_events:
                self._add_event_row(event)
        
        # Show "No events" message if no events at all
        if not today_events and not upcoming_events:
            no_events = Gtk.Label(label="No events")
            no_events.add_css_class("dim-label")
            no_events.set_margin_top(20)
            no_events.set_margin_bottom(20)
            self.events_list.append(no_events)
    
    def _add_event_row(self, event: Event):
        """Add an event row to the events list."""
        row = Adw.ActionRow()
        row.set_title(event.summary)
        
        # Store event reference in the row
        row.event = event
        
        # Subtitle with time and location
        subtitle_parts = []
        if not event.all_day:
            subtitle_parts.append(event.start_time.strftime("%H:%M"))
        if event.location:
            subtitle_parts.append(event.location)
        
        if subtitle_parts:
            row.set_subtitle(" • ".join(subtitle_parts))
        
        # Calendar indicator
        calendar_label = Gtk.Label(label=event.calendar_name)
        calendar_label.add_css_class("event-calendar")
        calendar_label.add_css_class("pill")
        row.add_suffix(calendar_label)
        
        # Add edit and delete buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.add_css_class("event-buttons")
        
        # Edit button
        edit_btn = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        edit_btn.add_css_class("flat")
        edit_btn.set_tooltip_text("Edit event")
        edit_btn.connect("clicked", lambda btn: self._edit_event(event))
        button_box.append(edit_btn)
        
        # Delete button
        delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("destructive-action")
        delete_btn.set_tooltip_text("Delete event")
        delete_btn.connect("clicked", lambda btn: self._delete_event(event))
        button_box.append(delete_btn)
        
        row.add_suffix(button_box)
        
        self.events_list.append(row)
    
    def _on_day_clicked(self, button):
        """Handle day button click."""
        date_str = button.get_name()
        self.selected_date = date.fromisoformat(date_str)
        self._update_calendar()  # Update calendar to show new selection
        self._update_events()
        self.emit('date-selected', self.selected_date)
    
    def _on_prev_month(self, button):
        """Handle previous month button."""
        if self.current_month.month == 1:
            self.current_month = self.current_month.replace(year=self.current_month.year - 1, month=12)
        else:
            self.current_month = self.current_month.replace(month=self.current_month.month - 1)
        self._update_calendar()
    
    def _on_next_month(self, button):
        """Handle next month button."""
        if self.current_month.month == 12:
            self.current_month = self.current_month.replace(year=self.current_month.year + 1, month=1)
        else:
            self.current_month = self.current_month.replace(month=self.current_month.month + 1)
        self._update_calendar()
    
    def _on_add_event(self, button):
        """Handle add event button."""
        dialog = EventDialog(
            self.get_root(), 
            self.calendar_manager, 
            self.selected_date
        )
        
        dialog.connect("close-request", self._on_event_dialog_closed, dialog, None)
        dialog.present()
    
    def _on_event_right_click(self, gesture, n_press, x, y, event):
        """Handle right-click on event (deprecated - now using buttons)."""
        # This method is kept for compatibility but no longer used
        # Right-click functionality is now replaced with edit/delete buttons
        pass
    
    def _show_event_menu(self, event: Event, x: float, y: float):
        """Show context menu for event (deprecated - now using buttons)."""
        # This method is kept for compatibility but no longer used
        # Context menu functionality is now replaced with edit/delete buttons
        self._edit_event(event)
    
    def _edit_event(self, event: Event):
        """Edit an existing event."""
        dialog = EventDialog(
            self.get_root(),
            self.calendar_manager,
            self.selected_date,
            event
        )
        
        dialog.connect("close-request", self._on_event_dialog_closed, dialog, event)
        dialog.present()
    
    def _delete_event(self, event: Event):
        """Delete an event."""
        if self.calendar_manager.remove_event(event):
            self._update_calendar()
            self._update_events()
            self.emit('event-removed', event)
    
    def _on_event_dialog_closed(self, dialog, dialog_obj, original_event):
        """Handle event dialog close."""
        if dialog_obj.result:
            if original_event:
                # Edit existing event
                if self.calendar_manager.edit_event(original_event, dialog_obj.result):
                    self._update_calendar()
                    self._update_events()
                    self.emit('event-edited', original_event, dialog_obj.result)
            else:
                # Add new event
                if self.calendar_manager.add_event(dialog_obj.result):
                    self._update_calendar()
                    self._update_events()
                    self.emit('event-added', dialog_obj.result)
        
        return False
    
    def set_selected_date(self, selected_date: date):
        """Set the selected date programmatically."""
        self.selected_date = selected_date
        self.current_month = selected_date.replace(day=1)
        self._update_calendar()
        self._update_events()
    
    def refresh(self):
        """Refresh the calendar data."""
        self.calendar_manager.reload_calendars()
        self._update_events() 
        self._update_calendar()
