from PyQt6 import QtWidgets, uic
from PyQt6.uic import loadUi
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
import sys
import subprocess
import platform
import os
import time

class SlideWorker(QObject):

    progress = pyqtSignal(int)  # Signal to update progress bar
    eta = pyqtSignal(str)      # Signal to update ETA
    finished = pyqtSignal()    # Signal when operation is complete

    def __init__(self, old_first, old_last, new_first, disk_path, sector_size):

        super().__init__()

        self.old_first = int(old_first)
        self.old_last = int(old_last)
        self.new_first = int(new_first)
        self.disk_path = disk_path
        self.sector_size = int(sector_size)

    def run(self):
        target_size = 1024 * 1024 * 1024  # 1 GiB in bytes
        block_size = self.sector_size  # Normally 512 bytes
        bytes_per_round = block_size * (target_size // block_size)  # 1 GiB in bytes
        print("bytes_per_round", bytes_per_round)
        partition_sectors = self.old_last - self.old_first
        print("partition_sectors: ", partition_sectors)
        if self.old_first == self.new_first:
            self.finished.emit()
            print("no displacement")
            return

        start_time = time.time()
        total_bytes = partition_sectors * block_size
        print("total_bytes: ", total_bytes)
        old_start = self.old_first * block_size
        print("old_start: ", old_start)
        new_first = self.new_first * block_size
        print("new_first: ", new_first)

        with open(self.disk_path, 'r+b') as disk:

            if self.old_first > self.new_first:  # Moving left
                for i in range(0, total_bytes, bytes_per_round):
                    chunk_end = min(bytes_per_round + i, total_bytes)
                    disk.seek(old_start + i)
                    data = disk.read(chunk_end - i)
                    disk.seek(new_first + i)
                    disk.write(data)
                    disk.flush()

                    # Progress update
                    progress = int((chunk_end / total_bytes) * 100)
                    self.progress.emit(progress)

                    # ETA calculation
                    elapsed_time = time.time() - start_time
                    bytes_written = chunk_end
                    if bytes_written > 0:
                        speed = bytes_written / elapsed_time  # bytes per second
                        remaining_bytes = total_bytes - bytes_written
                        eta_seconds = remaining_bytes / speed if speed > 0 else 0
                        self.emit_eta(eta_seconds)

            elif self.old_first < self.new_first:  # Moving right
                for i in range(total_bytes, 0, -bytes_per_round):
                    chunk_start = max(0, i - bytes_per_round)
                    disk.seek(old_start + chunk_start)
                    data = disk.read(i - chunk_start)
                    disk.seek(new_first + chunk_start)
                    disk.write(data)
                    disk.flush()

                    # Progress update
                    progress = int(((total_bytes - chunk_start) / total_bytes) * 100)
                    self.progress.emit(progress)

                    # ETA calculation
                    elapsed_time = time.time() - start_time
                    bytes_written = total_bytes - chunk_start
                    if bytes_written > 0:
                        speed = bytes_written / elapsed_time  # bytes per second
                        remaining_bytes = total_bytes - bytes_written
                        eta_seconds = remaining_bytes / speed if speed > 0 else 0
                        self.emit_eta(eta_seconds)

        disk.close()
        self.progress.emit(100)
        self.emit_eta(0)
        self.finished.emit()

    def emit_eta(self, seconds):

        days = int(seconds // (24 * 3600))
        hours = int((seconds % (24 * 3600)) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        eta_str = f"{days}D, {hours}H, {minutes}M, {secs}S"
        self.eta.emit(eta_str)

def le(hex_str):
    hex_str = str(hex_str)
    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str

    # Convert the hex string to a bytes object.
    # bytes.fromhex() expects the string to have an even number of digits.
    byte_data = bytes.fromhex(hex_str)
        
    # Convert the byte data from little-endian to an integer.
    return int.from_bytes(byte_data, byteorder='little')
      
def el(n):
    # Convert integer to hexadecimal string without '0x' prefix
    hex_str = hex(int(n))[2:]
        
    # Pad the hex string to make its length even (for byte alignment)
    padded_hex = hex_str.zfill(len(hex_str) + len(hex_str) % 2)
        
    # Create little-endian hex string
    little_endian_hex = ''
    for i in range(0, len(padded_hex), 2):
        little_endian_hex = padded_hex[i:i+2] + little_endian_hex
        
    return little_endian_hex



def get_disks_and_sectors():
    if os.name == 'posix' and platform.system() == 'Linux':
        try:
            result = subprocess.run(['lsblk', '-n', '-o', 'NAME,SECTORS,PHY-SEC', '-d'],
                                  capture_output=True, text=True, check=True)
            disk_list = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                        name, sectors, bytes_per_sector = parts[0], parts[1], parts[2]
                        disk_list.append([f"/dev/{name}", int(bytes_per_sector), int(sectors)])
            return disk_list
        except (subprocess.CalledProcessError, FileNotFoundError):
            return [["Error", 0, 0]]
    
    elif os.name == 'nt':  # Windows
        try:
            result = subprocess.run(['wmic', 'diskdrive', 'get', 'DeviceID,BytesPerSector,TotalSectors'],
                                  capture_output=True, text=True, check=True)
            disk_list = []
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            for line in lines:
                line = line.strip()
                if line:  # Ignore empty lines
                    # Split on whitespace and filter out empty strings
                    parts = [p for p in line.split() if p]
                    if len(parts) == 3 and parts[0].isdigit() and parts[2].isdigit():
                        bytes_per_sector, device_id, sectors = parts[0], parts[1], parts[2]
                        disk_list.append([device_id, int(bytes_per_sector), int(sectors)])
            return disk_list
        except (subprocess.CalledProcessError, FileNotFoundError):
            return [["Error", 0, 0]]
    
    else:
        return [["Unsupported OS", 0, 0]]

class PartitionWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.partitions = []  # (start, end, name)
        self.original_partitions = []  # Store original positions
        self.disk_range = [0, 1]  # [start, end] of entire disk
        self.selected_index = -1  # Index of selected partition (persistent)
        self.drag_start_x = 0
        self.drag_start_pos = None
        self.last_moved_index = -1  # Track the last moved partition
        self.is_dragging = False  # Flag to track dragging state
        self.main_window = parent
        while self.main_window and not isinstance(self.main_window, MainWindow):
            self.main_window = self.main_window.parent()
        self.setMouseTracking(True)

    def set_data(self, partitions, disk_range):
        self.partitions = partitions.copy()
        self.original_partitions = partitions.copy()
        self.disk_range = disk_range
        self.selected_index = -1
        self.last_moved_index = -1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        padding = 2
        avail_width = self.width() - 2 * padding
        avail_height = self.height() - 2 * padding
        disk_start, disk_end = self.disk_range
        disk_size = disk_end - disk_start

        painter.setBrush(QColor("#d0d0d0"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(padding, padding, avail_width, avail_height))

        for i, (start, end, name) in enumerate(self.partitions):
            x = padding + ((start - disk_start) / disk_size) * avail_width
            width = ((end - start) / disk_size) * avail_width
            if width < 5:
                width = 5

            rect = QRectF(x, padding, width, avail_height)
            color = QColor("#FFA500" if i == 0 else "#6495ED" if i % 2 else "#32CD32")

            if i == self.selected_index:
                shadow_color = QColor(0, 0, 0, 100)
                painter.setBrush(shadow_color)
                painter.setPen(Qt.PenStyle.NoPen)
                shadow_rect = QRectF(x + 2, padding + 2, width, avail_height + 2)
                painter.drawRoundedRect(shadow_rect, 3, 3)
                color = color.darker(120)
            
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#000000"), 2, Qt.PenStyle.SolidLine))
            painter.drawRoundedRect(rect, 3, 3)

            luminance = (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255
            text_color = QColor(255, 255, 255) if luminance < 0.5 else QColor(0, 0, 0)
            painter.setPen(text_color)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            orig_start, orig_end, _ = self.original_partitions[i]
            sectors = orig_end - orig_start
            gib = (sectors * self.main_window.sector_size) / (1024 ** 3)
            text_rect = rect.adjusted(5, 2, -5, -2)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, 
                             f"{name}\n{sectors} sectors\n{gib:.2f} GiB")

    def mousePressEvent(self, event):
        pos = event.pos().toPointF()
        padding = 2
        avail_width = self.width() - 2 * padding
        disk_start, disk_end = self.disk_range
        disk_size = disk_end - disk_start

        previous_selection = self.selected_index
        for i, (start, end, _) in enumerate(self.partitions):
            x = padding + ((start - disk_start) / disk_size) * avail_width
            width = ((end - start) / disk_size) * avail_width
            if width < 5:
                width = 5
            rect = QRectF(x, padding, width, self.height() - 2 * padding)
            if rect.contains(pos):
                if self.last_moved_index != -1 and self.last_moved_index != i:
                    self.partitions[self.last_moved_index] = self.original_partitions[self.last_moved_index]
                    self.last_moved_index = -1
                self.selected_index = i
                self.drag_start_x = pos.x()
                self.drag_start_pos = (start, end)
                self.is_dragging = True
                if self.main_window and previous_selection != self.selected_index:
                    self.main_window.selection()
                break
        else:
            if self.selected_index != -1 and self.main_window:
                self.main_window.nonselection()
            self.selected_index = -1
            self.is_dragging = False

        self.update()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self.is_dragging or self.selected_index == -1:
            return

        pos = event.pos().toPointF()
        padding = 2
        avail_width = self.width() - 2 * padding
        disk_start, disk_end = self.disk_range
        disk_size = disk_end - disk_start

        delta_x = pos.x() - self.drag_start_x
        delta_units = (delta_x / avail_width) * disk_size

        start, end = self.drag_start_pos
        size = end - start
        new_start = round(start + delta_units)
        new_end = new_start + size

        new_start = max(disk_start, min(new_start, disk_end - size))
        new_end = new_start + size

        mouse_disk_pos = disk_start + (pos.x() - padding) / avail_width * disk_size
        for i, (other_start, other_end, _) in enumerate(self.partitions):
            if i == self.selected_index:
                continue
            if delta_units < 0 and new_start < other_end and new_end > other_start:
                new_start = other_end
                new_end = new_start + size
                if mouse_disk_pos < other_start:
                    available_start = disk_start
                    for j, (check_start, check_end, _) in enumerate(self.partitions):
                        if j != self.selected_index and j != i and check_end <= other_start:
                            available_start = max(available_start, check_end)
                    if other_start - available_start >= size:
                        new_end = other_start
                        new_start = new_end - size
                    else:
                        new_start = other_end
                        new_end = new_start + size
            elif delta_units > 0 and new_end > other_start and new_start < other_end:
                new_end = other_start
                new_start = new_end - size
                if mouse_disk_pos > other_end:
                    available_end = disk_end
                    for j, (check_start, check_end, _) in enumerate(self.partitions):
                        if j != self.selected_index and j != i and check_start >= other_end:
                            available_end = min(available_end, check_start)
                    if available_end - other_end >= size:
                        new_start = other_end
                        new_end = new_start + size
                    else:
                        new_end = other_start
                        new_start = new_end - size

        new_start = round(max(disk_start, min(new_start, disk_end - size)))
        new_end = new_start + size

        self.partitions[self.selected_index] = (new_start, new_end, self.partitions[self.selected_index][2])
        self.drag_start_x = pos.x()
        self.drag_start_pos = (new_start, new_end)

        if self.main_window:
            self.main_window.drag()

        self.update()

    def mouseReleaseEvent(self, event):
        if self.is_dragging and self.selected_index != -1:
            self.last_moved_index = self.selected_index
            self.is_dragging = False
        self.update()

    def update_position(self, new_start=None, new_end=None, offset=None):
        if self.selected_index == -1:
            return

        disk_start, disk_end = self.disk_range
        orig_start, orig_end, name = self.original_partitions[self.selected_index]
        curr_start, curr_end, _ = self.partitions[self.selected_index]
        size = orig_end - orig_start

        try:
            if new_start is not None:
                new_start = round(float(new_start))
                new_end = new_start + size
            elif new_end is not None:
                new_end = round(float(new_end))
                new_start = new_end - size
            elif offset is not None:
                offset = round(float(offset))
                new_start = orig_start + offset  # Offset from original position
                new_end = new_start + size
            else:
                return
        except ValueError:
            return

        new_start = max(disk_start, min(new_start, disk_end - size))
        new_end = new_start + size

        for i, (other_start, other_end, _) in enumerate(self.partitions):
            if i == self.selected_index:
                continue
            if new_start < other_end and new_end > other_start:
                if offset is not None and offset < 0:
                    new_start = other_end
                    new_end = new_start + size
                elif offset is not None and offset > 0:
                    new_end = other_start
                    new_start = new_end - size
                else:
                    new_start = curr_start
                    new_end = curr_end
                break

        new_start = max(disk_start, min(new_start, disk_end - size))
        new_end = new_start + size

        self.partitions[self.selected_index] = (new_start, new_end, name)
        self.last_moved_index = self.selected_index
        self.update()

    def select_partition(self, partition_name):
        """Update selected_index based on partition name from combobox."""
        previous_selection = self.selected_index
        for i, (_, _, name) in enumerate(self.partitions):
            if name == partition_name:
                if self.last_moved_index != -1 and self.last_moved_index != i:
                    self.partitions[self.last_moved_index] = self.original_partitions[self.last_moved_index]
                    self.last_moved_index = -1
                self.selected_index = i
                if self.main_window and previous_selection != self.selected_index:
                    self.main_window.selection()
                break
        else:
            # If no match (e.g., empty or invalid selection), deselect
            if self.selected_index != -1 and self.main_window:
                self.main_window.nonselection()
            self.selected_index = -1
        self.update()

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.ui_path = "1.ui"
        loadUi(self.ui_path, self)

        self.partition_display = PartitionWidget(self.widget)
        self.partition_display.setGeometry(0, 0, 800, 100)

        self.progressBar.setValue(0)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)

        self.paths = get_disks_and_sectors()
        for i in range(0, len(self.paths)):
            self.d_select.addItem(self.paths[i][0])

        self.pushButton_2.setIcon(QIcon("refresh.png"))
        self.pushButton_2.clicked.connect(self.refresh)
        
        self.start_button.clicked.connect(self.pre)
        
        self.p_select.currentTextChanged.connect(self.handle_partition_selection)
        self.new_start_sec.returnPressed.connect(self.update_from_lineedits)
        self.new_end_sec.returnPressed.connect(self.update_from_lineedits)
        self.offset_line.returnPressed.connect(self.update_from_lineedits)

        self.current_info = None
        self.part_selected = None
        self.current_new_first = None
        self.current_path = None
        # Apply style sheet
        self.partition_display.setStyleSheet("""
            PartitionWidget {
                background-color: #f0f0f0;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
            }
        """)

        self.d_select.currentTextChanged.connect(
            lambda: self.Load(self.m_select.currentText(), self.d_select.currentText())
        )

        self.thread = None
        self.worker = None

    def pre(self):
        if (self.paths[self.d_select.currentIndex()][0] != "" and 
            self.p_select.currentIndex() != "" and 
            self.start_sec.text() != "" and 
            self.option == "MBR"): #a whole if statement lol, dont get it wrong
            self.Start(self.option, self.paths[self.d_select.currentIndex()][0], 
                       self.p_select.currentIndex(), self.new_start_sec.text()) #current partition selected is c2, it's defined in ui file, new starting sector

    def refresh(self):
        self.paths = get_disks_and_sectors()
        self.d_select.clear()
        for i in range(len(self.paths)):
            self.d_select.addItem(self.paths[i][0])

    def selection(self):
        self.selected = list(self.partitions[next((i for i, t in enumerate(self.partitions) if self.partition_display.partitions[self.partition_display.selected_index][2] in t), None)])

        self.selected[0] = int(self.selected[0])
        self.selected[1] = int(self.selected[1])
        self.p_select.setCurrentText(self.partition_display.partitions[self.partition_display.selected_index][2])

        self.start_sec.setText(str(self.selected[0]))
        self.start_gb.setText(f"{((self.selected[0] * self.sector_size) / (1024 ** 3)):.2f} Gib")
        self.end_sec.setText(str(self.selected[1]))
        self.end_gb.setText(f"{((self.selected[1] * self.sector_size) / (1024 ** 3)):.2f} Gib")
        self.total_sec.setText(str(self.selected[1]-self.selected[0]))
        self.total_gb.setText(f"{(((self.selected[1]-self.selected[0]) * self.sector_size) / (1024 ** 3)):.2f} Gib")
        self.drag()
        #self.progressBar.setMinimum(int(self.total_sec.text()))

    def drag(self):
        start, end, name = self.partition_display.partitions[self.partition_display.selected_index]
        self.new_start_sec.setText(str(start))
        self.new_end_sec.setText(str(end))
        if start < self.selected[0]:
            self.offset = self.selected[0]-start
            self.offset_line.setText(f"-{self.offset}")
            self.offset_sec.setText(f"-{self.offset}")
            self.offset_gb.setText(f"-{((self.offset * self.sector_size) / (1024 ** 3)):.2f}")

        elif start > self.selected[0]:
            self.offset = start-self.selected[0]
            self.offset_line.setText(f"+{self.offset}")
            self.offset_sec.setText(f"+{self.offset}")
            self.offset_gb.setText(f"+{((self.offset * self.sector_size) / (1024 ** 3)):.2f}")

    def update_from_lineedits(self):
        sender = self.sender()
        if sender == self.new_start_sec:
            self.partition_display.update_position(new_start=self.new_start_sec.text())
        elif sender == self.new_end_sec:
            self.partition_display.update_position(new_end=self.new_end_sec.text())
        elif sender == self.offset_line:
            self.partition_display.update_position(offset=self.offset_line.text())
        self.drag()

    def handle_partition_selection(self, partition_name):
        self.partition_display.select_partition(partition_name)

    def nonselection(self):
        selected = False

    def Load(self, method, path):
        self.p_select.clear()
        if method == "Auto":
            method = self.id(path)
        if method == "MBR":
            self.option = "MBR"
            with open(r'{}'.format(path), 'rb') as disk:
                disk.seek(0)
                disk.read(512)
            self.MBR_DATA = self.MBR(self.d_select.currentText()) #[rawH,DiskSig,PartitionTable,Signature,Partition_Tables][Cylinder, Head, Sector, Type_B, Type, Cylinder2, Head2, Sector2, FirstSector, TotalSector, LastSector]

            self.partitions = []

            for i in range(0, len(self.MBR_DATA[4])):
                self.partitions.append((self.MBR_DATA[4][i][8], self.MBR_DATA[4][i][10], self.MBR_DATA[4][i][4]))

            disk_range = [1, (self.paths[self.d_select.currentIndex()][2])+1]

            self.sector_size = self.paths[self.d_select.currentIndex()][1]
            self.partition_display.set_data(self.partitions, disk_range)
            for i in range(0, len(self.partitions)):
                self.p_select.addItem(self.partitions[i][2])            
        else:
            QMessageBox.critical(self, 'Error', "Unsupported partition scheme!")

    def id(self, path):
        # Simplified identification (implement actual detection)
        return "MBR"

    def GPT(self, disk_path):
        with open(r'{}'.format(disk_path), 'rb') as disk:
            disk.seek(512)
            raw = disk.read(512).hex()

        def bytes_le_to_guid(hex_str):
            # Convert hex string to bytes
            b = bytes.fromhex(hex_str)

            # Extract fields and swap endianness where needed
            part1 = b[:4][::-1].hex()  # Little-endian (4 bytes)
            part2 = b[4:6][::-1].hex()  # Little-endian (2 bytes)
            part3 = b[6:8][::-1].hex()  # Little-endian (2 bytes)
            part4 = b[8:10].hex()       # Big-endian (2 bytes)
            part5 = b[10:].hex()        # Big-endian (6 bytes)

            # Format as standard GUID
            return f"{part1}-{part2}-{part3}-{part4}-{part5}"

        def find_partition_type(guid):
            partition_types = [
                {"GUID": "00000000-0000-0000-0000-000000000000", "Description": "Unused entry"},
                {"GUID": "024DEE41-33E7-11D3-9D69-0008C781F39F", "Description": "MBR partition scheme"},
                {"GUID": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B", "Description": "EFI System partition"},
                {"GUID": "21686148-6449-6E6F-744E-656564454649", "Description": "BIOS boot partition"},
                {"GUID": "D3BFE2DE-3DAF-11DF-BA40-E3A556D89593", "Description": "Intel Fast Flash (iFFS) partition (for Intel Rapid Start technology)"},
                {"GUID": "F4019732-066E-4E12-8273-346C5641494F", "Description": "Sony boot partition"},
                {"GUID": "BFBFAFE7-A34F-448A-9A5B-6213EB736C22", "Description": "Lenovo boot partition"},
                {"GUID": "E3C9E316-0B5C-4DB8-817D-F92DF00215AE", "Description": "Microsoft Reserved Partition (MSR)"},
                {"GUID": "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7", "Description": "Basic data partition"},
                {"GUID": "5808C8AA-7E8F-42E0-85D2-E1E90434CFB3", "Description": "Logical Disk Manager (LDM) metadata partition"},
                {"GUID": "AF9B60A0-1431-4F62-BC68-3311714A69AD", "Description": "Windows Storage Spaces partition"},
                {"GUID": "0FC63DAF-8483-4772-8E79-3D69D8477DE4", "Description": "Linux filesystem data"},
                {"GUID": "A19D880F-05FC-4D3B-A006-743F0F84911E", "Description": "Linux RAID partition"},
                {"GUID": "0657FD6D-A4AB-43C4-84E5-0933C84B4F4F", "Description": "Linux swap partition"},
                {"GUID": "E6D6D379-F507-44C2-A23C-238F2A3DF928", "Description": "Linux Logical Volume Manager (LVM) partition"},
                {"GUID": "933AC7E1-2EB4-4F13-B844-0E14E2AEF915", "Description": "Linux /home partition"},
                {"GUID": "3B8F8425-20E0-4F3B-907F-1A25A76F98E8", "Description": "Linux /srv (server data) partition"},
                {"GUID": "7FFEC5C9-2D00-49B7-8941-3EA10A5586B7", "Description": "Linux plain dm-crypt partition"},
                {"GUID": "CA7D7CCB-63ED-4C53-861C-1742536059CC", "Description": "Linux LUKS partition"},
                {"GUID": "8DA63339-0007-60C0-C436-083AC8230908", "Description": "Linux reserved"},
                {"GUID": "A2A0D0EB-E5B9-3344-87C0-68B6B72699C7", "Description": "FreeBSD disklabel"},
                {"GUID": "516E7CB4-6ECF-11D6-8FF8-00022D09712B", "Description": "FreeBSD boot partition"},
                {"GUID": "516E7CB5-6ECF-11D6-8FF8-00022D09712B", "Description": "FreeBSD data partition"},
                {"GUID": "516E7CB6-6ECF-11D6-8FF8-00022D09712B", "Description": "FreeBSD swap partition"},
                {"GUID": "516E7CB8-6ECF-11D6-8FF8-00022D09712B", "Description": "FreeBSD UFS partition"},
                {"GUID": "516E7CB7-6ECF-11D6-8FF8-00022D09712B", "Description": "FreeBSD ZFS partition"},
                {"GUID": "516E7CBA-6ECF-11D6-8FF8-00022D09712B", "Description": "FreeBSD Vinum volume manager partition"},
                {"GUID": "48465300-0000-11AA-AA11-00306543ECAC", "Description": "Apple HFS+ partition"},
                {"GUID": "55465300-0000-11AA-AA11-00306543ECAC", "Description": "Apple UFS partition"},
                {"GUID": "6A898CC3-1DD2-11B2-99A6-080020736631", "Description": "Apple ZFS partition"},
                {"GUID": "52414944-0000-11AA-AA11-00306543ECAC", "Description": "Apple RAID partition"},
                {"GUID": "52414944-5F4F-11AA-AA11-00306543ECAC", "Description": "Apple RAID offline partition"},
                {"GUID": "426F6F74-0000-11AA-AA11-00306543ECAC", "Description": "Apple Boot partition"},
                {"GUID": "4C616265-6C00-11AA-AA11-00306543ECAC", "Description": "Apple Label partition"},
                {"GUID": "5265636F-7665-11AA-AA11-00306543ECAC", "Description": "Apple TV Recovery partition"},
                {"GUID": "53746F72-6167-11AA-AA11-00306543ECAC", "Description": "Apple Core Storage (i.e. Lion FileVault) partition"},
                {"GUID": "6A82CB45-1DD2-11B2-99A6-080020736631", "Description": "Solaris boot partition"},
                {"GUID": "6A85CF4D-1DD2-11B2-99A6-080020736631", "Description": "Solaris root partition"},
                {"GUID": "6A87C46F-1DD2-11B2-99A6-080020736631", "Description": "Solaris /usr partition"},
                {"GUID": "6A8B642B-1DD2-11B2-99A6-080020736631", "Description": "Solaris swap partition"},
                {"GUID": "6A8D2AC7-1DD2-11B2-99A6-080020736631", "Description": "Solaris backup partition"},
                {"GUID": "6A898CC3-1DD2-11B2-99A6-080020736631", "Description": "Solaris /var partition"},
                {"GUID": "6A8EF2E9-1DD2-11B2-99A6-080020736631", "Description": "Solaris /home partition"},
                {"GUID": "6A90BA39-1DD2-11B2-99A6-080020736631", "Description": "Solaris alternate sector"},
                {"GUID": "6A9283A5-1DD2-11B2-99A6-080020736631", "Description": "Solaris reserved partition"},
                {"GUID": "6A945A3B-1DD2-11B2-99A6-080020736631", "Description": "Solaris root pool"},
                {"GUID": "6A9630D1-1DD2-11B2-99A6-080020736631", "Description": "Solaris boot pool"},
                {"GUID": "49F48D32-B10E-11DC-B99B-0019D1879648", "Description": "NetBSD swap partition"},
                {"GUID": "49F48D5A-B10E-11DC-B99B-0019D1879648", "Description": "NetBSD FFS partition"},
                {"GUID": "49F48D82-B10E-11DC-B99B-0019D1879648", "Description": "NetBSD LFS partition"},
                {"GUID": "49F48DAA-B10E-11DC-B99B-0019D1879648", "Description": "NetBSD RAID partition"},
                {"GUID": "49F48DD2-B10E-11DC-B99B-0019D1879648", "Description": "NetBSD Concatenated partition"},
                {"GUID": "2DB519C4-B10F-11DC-B99B-0019D1879648", "Description": "NetBSD encrypted partition"},
                {"GUID": "FE3A2A5D-4F32-41A7-B725-ACCC3285A309", "Description": "VMware VMFS partition"},
                {"GUID": "AA31E02A-400F-11DB-9590-000C2911D1B8", "Description": "VMware reserved partition"},
                {"GUID": "9D275380-40AD-11DB-BF97-000C2911D1B8", "Description": "VMware kcore crash partition"},
                {"GUID": "11D2F81B-FD4F-459B-9ADB-9091ED7E593F", "Description": "XenServer Linux partition"},
                {"GUID": "5B193300-FC78-40CD-8002-E86C45580B47", "Description": "Microsoft Basic Data partition"},
                {"GUID": "0376FF8D-D1A5-11E3-8E7D-001B21B9EADD", "Description": "Ceph OSD partition"},
                {"GUID": "45B0969E-9B03-4F30-B4C6-5EC00CEFF106", "Description": "Ceph disk in creation"},
                {"GUID": "4FBD7E29-9D25-41B8-AFD0-062C0CEFF05D", "Description": "Ceph journal"},
                {"GUID": "89C57F98-2FE5-4DC0-89C1-F3AD0CEFF2BE", "Description": "Ceph crypt"},
                {"GUID": "FB3AABF9-D6F9-46D8-9F9D-D6A4E56C5E36", "Description": "Ceph block"},
                {"GUID": "CAFECAFE-9B03-4F30-B4C6-5EC00CEFF106", "Description": "Ceph block DB"},
                {"GUID": "30D3B3C4-9B03-4F30-B4C6-5EC00CEFF106", "Description": "Ceph block write-ahead log"}
            ]
            for partition in partition_types:
                if partition["GUID"].lower() == guid.lower():  # Case-insensitive comparison
                    return partition["Description"]
            return "Unknow: " + guid


        signature = raw[:16]
        signature_ascii = bytearray.fromhex(signature).decode()
        revision = raw[16:24]
        version = str(revision[5:6]) + "." + str(revision[6:8])
        header_size = le(raw[24:32])
        CRC32 = raw[32:40]
        reserved = raw[40:48]
        current_lba = le(raw[48:64])
        backup_lba = le(raw[64:80])
        first_partition = le(raw[80:96])
        last_lba = le(raw[96:112])
        GUID = raw[112:144]
        partition_entry_starting_lba = le(raw[144:160])
        partition_entry_count = le(raw[160:168])
        partition_entry_size = le(raw[168:176])
        partition_array_CRC32 = raw[176:184]

        with open(r'{}'.format(disk_path), 'rb') as disk:
            disk.seek(partition_entry_starting_lba * 512)
            raw2 = disk.read(partition_entry_count * partition_entry_size).hex()


        def partition_groups(hex_string, partition_entry_size, partition_entry_count):

            expected_length = partition_entry_size * partition_entry_count
            if len(hex_string) != expected_length:
                raise ValueError(f"The hex string must be of length {expected_length} (partition_entry_size * partition_entry_count).")

            groups = [hex_string[i:i+partition_entry_count] for i in range(0, len(hex_string), partition_entry_size)]

            empty_count = sum(1 for group in groups if all(c == '0' for c in group))

            non_empty_groups = [group for group in groups if not all(c == '0' for c in group)]
            
            return empty_count, non_empty_groups


        empty_count, non_empty_groups = partition_groups(raw2, partition_entry_size * 2, partition_entry_count)

        #Partition Parse(PP)
        def PP(data):
            PartitionTypeGUID = find_partition_type(bytes_le_to_guid(data[:32]))
            UniquePartitionGUID = data[32:64]
            StartingLBA = le(data[64:80])
            EndingLBA = le(data[80:96])
            Attributes = data[96:112]
            binary_attri = bin(int(Attributes, 16))[2:].zfill(len(Attributes) * 4)
            if binary_attri[:1] != "0":
                Required_Partition = True
            else:
                Required_Partition = False
            if binary_attri[1:2] != "0":
                No_Block_IO_Protocol = True
            else:
                No_Block_IO_Protocol = False
            if binary_attri[2:3] != "0":
                Legacy_BIOS_Bootable = True
            else:
                Legacy_BIOS_Bootable = False
            PartitionName = data[112:256]
            
            return PartitionTypeGUID, UniquePartitionGUID, StartingLBA, EndingLBA, Attributes, PartitionName, Required_Partition, No_Block_IO_Protocol, Legacy_BIOS_Bootable
            
        GPTs = {}
        for i in range(0, partition_entry_count - empty_count):
            PartitionTypeGUID, UniquePartitionGUID, StartingLBA, EndingLBA, Attributes, PartitionName, Required_Partition, No_Block_IO_Protocol, Legacy_BIOS_Bootable = PP(non_empty_groups[i])
            GPTs[f'Partition{i}'] = [i, PartitionTypeGUID, UniquePartitionGUID, StartingLBA, EndingLBA, [Attributes, Required_Partition, No_Block_IO_Protocol, Legacy_BIOS_Bootable], bytearray.fromhex(PartitionName).decode()]
        return [signature, signature_ascii, revision, header_size, CRC32, reserved, current_lba, backup_lba, first_partition, last_lba, GUID, partition_entry_starting_lba, partition_entry_count, partition_entry_size, partition_array_CRC32, GPTs]

    def MBR(self, disk_path):
        with open(r'{}'.format(disk_path), 'rb') as disk:
            # Read the first 512 bytes
            rawB = disk.read(512)

        rawH = rawB.hex()

        def type_check(B):
            partition_types = [
            ['00', 'Empty or Unused'],
            ['01', 'FAT12'],
            ['02', 'XENIX root'],
            ['03', 'XENIX usr'],
            ['04', 'FAT16 (Small)'],
            ['05', 'Extended Partition'],
            ['06', 'FAT16'],
            ['07', 'NTFS / HPFS / exFAT'],
            ['08', 'AIX bootable'],
            ['09', 'AIX data'],
            ['0A', 'OS/2 Boot Manager'],
            ['0B', 'FAT32 (CHS)'],
            ['0C', 'FAT32 (LBA)'],
            ['0E', 'FAT16 (LBA)'],
            ['0F', 'Extended Partition (LBA)'],
            ['10', 'OPUS'],
            ['11', 'Hidden FAT12'],
            ['12', 'Compaq diagnostcs'],
            ['14', 'FAT16 (LBA)'],
            ['16', 'Hidden FAT16'],
            ['17', 'Hidden NTFS'],
            ['1B', 'Hidden FAT32'],
            ['1C', 'Hidden FAT32 (LBA)'],
            ['1E', 'Hidden FAT16 (LBA)'],
            ['24', 'NEC DOS'],
            ['39', 'Plan 9'],
            ['3C', 'PartitionMagic recovery'],
            ['40', 'Venix 80286'],
            ['41', 'Linux/MINIX'],
            ['42', 'Linux Swap'],
            ['43', 'Linux Ext2/Ext3 (Old format)'],
            ['44', 'Linux Ext2/Ext3 (New format)'],
            ['83', 'Linux ext FS'],
            ['84', 'Linux swap / Solaris'],
            ['8E', 'Linux LVM'],
            ['93', 'Amoeba'],
            ['A0', 'IBM Thinkpad hidden'],
            ['A5', 'FreeBSD'],
            ['A6', 'OpenBSD'],
            ['A8', 'Mac OS X'],
            ['A9', 'NetBSD'],
            ['AF', 'Mac OS X HFS+'],
            ['B7', 'BSDI'],
            ['B8', 'Boot Manager'],
            ['BE', 'Solaris Boot Partition'],
            ['BF', 'Solaris / OpenIndiana'],
            ['C0', 'NTFS Boot Partition'],
            ['C1', 'FreeBSD boot'],
            ['C4', 'TrueCrypt volume'],
            ['C7', 'Windows 7 recovery'],
            ['D1', 'OpenBSD bootstrap'],
            ['D3', 'GParted'],
            ['D5', 'FreeBSD UFS2'],
            ['D6', 'Solaris (x86) partition'],
            ['D7', 'OpenBSD partition'],
            ['E1', 'Linux RAID'],
            ['E2', 'Linux LVM2'],
            ['E3', 'Linux EVMS'],
            ['E4', 'MS-DOS 6.0'],
            ['E5', 'OpenDOS'],
            ['E6', 'OS/2 Boot Manager'],
            ['E7', 'Non-OS/2 Boot Manager'],
            ['EB', 'FAT16 (LBA) (exFAT)'],
            ['EC', 'Windows 98 SE'],
            ['EE', 'GPT Protective'],
            ['EF', 'EFI System Partition'],
            ['F0', 'Microsoft Reserved'],
            ['F2', 'Linux Swap (used by newer Linux versions)'],
            ['F4', 'Microsoft Windows recovery partition'],
            ['F6', 'HPFS/NTFS'],
            ['F7', 'HPFS/NTFS (Boot)'],
            ['F8', 'OEM proprietary'],
            ['F9', 'BSD']
            ]
            for i in range(0, len(partition_types)):
                if B == partition_types[i][0]:
                    return partition_types[i][1]
            return "Unknow"


        def partition(raw):
            if raw == "00000000000000000000000000000000":
                return "Empty"
            elif len(raw) != 32:
                QMessageBox.critical(self,'MBR Error', "Unexpected length, please exit program")
                exit()

            if int(raw[:2]) == 80:
                bootable = "not bootable"
            elif int(raw[:2]) == 00:
                bootable = "not bootable"
            else:
                QMessageBox.critical(self,'MBR Error', "UnExpected PartitionTable Headerraw, please exit program")
                exit()
            Cylinder = raw[2:4]
            Head = raw[4:6]
            Sector = raw[6:8]
            Type_B = raw[8:10]
            Type = type_check(Type_B)
            Cylinder2 = raw[10:12]
            Head2 = raw[12:14]
            Sector2 = raw[14:16]
            FirstSector = le(raw[16:24])
            TotalSector = le(raw[24:32])
            LastSector = FirstSector + TotalSector
            return [Cylinder, Head, Sector, Type_B, Type, Cylinder2, Head2, Sector2, FirstSector, TotalSector, LastSector]

        boot_code = rawH[:880]
        DiskSig = rawH[880:892]
        PartitionTable = rawH[892:1020]
        PartitionTable_B = rawH[3568:4080]
        Signature = rawH[-4:]
        p1 = PartitionTable[:32]
        p2 = PartitionTable[32:64]
        p3 = PartitionTable[64:96]
        p4 = PartitionTable[-32:]

        
        part1 = partition(p1)
        part2 = partition(p2)
        part3 = partition(p3)
        part4 = partition(p4)
        Partition_Tables = []

        if part1 != "Empty":
            Partition_Tables.append(part1)
        if part2 != "Empty":
            Partition_Tables.append(part2)
        if part3 != "Empty":
            Partition_Tables.append(part3)
        if part4 != "Empty":
            Partition_Tables.append(part4)

        return [rawH, DiskSig, PartitionTable, Signature, Partition_Tables] #Partition_Tables are parsed, in form of list of [Cylinder, Head, Sector, Type_B, Type, Cylinder2, Head2, Sector2, FirstSector, TotalSector, LastSector]



    def slide(self, old_first, old_last, new_first, disk_path):
        if self.thread is not None and self.thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress", "A slide operation is already running.")
            return

        self.thread = QThread()
        self.worker = SlideWorker(old_first, old_last, new_first, disk_path, self.sector_size)
        self.worker.moveToThread(self.thread)
        self.worker.progress.connect(self.update_progress)  # Assuming these signals exist
        self.worker.eta.connect(self.update_eta)
        self.worker.finished.connect(self.slide_finished)  # Connect to completion handler
        self.thread.started.connect(self.worker.run)
        self.start_button.setEnabled(False)  # Disable UI during operation
        self.thread.start()

    def update_progress(self, value):
        self.progressBar.setValue(value)

    def update_eta(self, eta_str):
        self.ETA.setText(eta_str)

    def slide_finished(self):
        # First, update the MBR
        self.update_mbr()
        # Then, clean up and update UI
        self.start_button.setEnabled(True)
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        print("Slide operation and MBR update completed")

    def update_mbr(self): #since it's using replace menthod, there is a chance for identical bytes getting replaced by partition table, but the chance is very very small and I'm lazy, so fix won't be introduced in the pre release, I will do it later
        
        if self.current_info is None or self.part_selected is None or self.current_new_first is None or self.current_path is None:
            print("Error: Missing information for MBR update")
            return

        New_First = self.current_new_first
        path = self.current_path
        print(f"Opening disk with path in update_mbr: {path}")
        try:
            disk = open(r'{}'.format(path), 'r+b', buffering=0)
            try:
                ptable = self.get_mbr_partition(self.current_info[2], self.part_selected) #get the specific raw partition table we want
                ptable_new = ptable.replace(ptable[16:24], (el(New_First)).ljust(8, "0"))
                
                print("ptable_new:", ptable_new)
                print("old mbr", self.current_info[0])

                mbr_new = self.current_info[0].replace(ptable, ptable_new)
                disk.seek(0)
                print("mbr_new:", mbr_new)
                disk.write(bytes.fromhex(mbr_new))

                disk.flush()
            finally:
                disk.close()  # Explicitly close the file
                print(f"Closed disk in update_mbr: {path}")
        except OSError as e:
            print(f"Failed to open or write to disk in update_mbr: {e}")
            return



    def get_mbr_partition(self, PartitionTable, part_number):
        if len(PartitionTable) != 128:
            print("partitionTable length incorrect, not equal to 128")
        part_size = 32


        start = part_number * part_size
        print("start:", start)
        end = start + part_size
        print("end:", end)
        print("PartitionTable[start:end]:", PartitionTable[start:end])
            # Return the desired part
        return PartitionTable[start:end]

    def Start(self, c1, path, c2, New_First):
        if c1 == "MBR":
            self.current_info = self.MBR(path)  # Assuming this retrieves MBR info
            # Store the variables for later use

            self.part_selected = c2
            self.current_new_first = New_First
            print("New_First", New_First)
            self.current_path = path
            # Start the slide operation
            self.slide(self.current_info[4][c2][8], self.current_info[4][c2][10], New_First, path)
            # Do NOT update MBR here
        elif c1 == "GPT":

            pass  # will add gpt suppoer later

if __name__ == '__main__':
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Windows")
    mainwindow = MainWindow()
    mainwindow.setFixedSize(800, 400)
    mainwindow.show()
    sys.exit(app.exec())
