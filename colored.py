import sys
import random
import google.generativeai as genai  # Requires: pip install google-generativeai
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                             QGroupBox, QTextEdit, QSpinBox, QFileDialog, QSplitter, QMessageBox)

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush
from datetime import datetime

class CPU:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.registers = {f"R{i}": 0 for i in range(8)}
        self.memory = {i: 0 for i in range(0, 256, 4)}  # Word-addressable memory
        self.pc = 0
        self.ir = None
        self.instructions = []
        self.alu_output = 0
        self.control_signals = {
            'fetch': False,
            'decode': False,
            'execute': False,
            'memory': False,
            'writeback': False
        }
        self.halted = False
        self.changed_registers = set()
        self.changed_memory = set()
        
    def load_program(self, program):
        self.instructions = program
        self.pc = 0
        self.ir = None  # Clear any previous instruction
        if hasattr(self, 'opcode'):
            delattr(self, 'opcode')
        if hasattr(self, 'operands'):
            delattr(self, 'operands')
        self.halted = False
        self.changed_registers.clear()
        self.changed_memory.clear()
        
    def fetch(self):
        if self.pc >= len(self.instructions):
            self.halted = True
            return False
            
        self.control_signals = {'fetch': True, 'decode': False, 'execute': False, 
                              'memory': False, 'writeback': False}
        self.ir = self.instructions[self.pc]
        return True
        
    def decode(self):
        self.control_signals = {'fetch': False, 'decode': True, 'execute': False, 
                              'memory': False, 'writeback': False}
        if not self.ir:
            return False
            
        parts = self.ir.split()
        self.opcode = parts[0].upper()
        self.operands = parts[1:] if len(parts) > 1 else []
        return True
        
    def execute(self):
        self.control_signals = {'fetch': False, 'decode': False, 'execute': True, 
                              'memory': False, 'writeback': False}
        if not hasattr(self, 'opcode'):
            return False
            
        self.changed_registers.clear()
        self.changed_memory.clear()
            
        try:
            if self.opcode == 'ADD':
                rd, rs1, rs2 = self.operands
                self.alu_output = self.registers[rs1] + self.registers[rs2]
                self.registers[rd] = self.alu_output
                self.changed_registers.add(rd)
                
            elif self.opcode == 'SUB':
                rd, rs1, rs2 = self.operands
                self.alu_output = self.registers[rs1] - self.registers[rs2]
                self.registers[rd] = self.alu_output
                self.changed_registers.add(rd)
                
            elif self.opcode == 'LOAD':
                rd, addr = self.operands
                addr = int(addr, 16) if addr.startswith('0x') else int(addr)
                self.control_signals['memory'] = True
                self.registers[rd] = self.memory.get(addr, 0)
                self.changed_registers.add(rd)
                
            elif self.opcode == 'STORE':
                rs, addr = self.operands
                addr = int(addr, 16) if addr.startswith('0x') else int(addr)
                self.control_signals['memory'] = True
                self.memory[addr] = self.registers[rs]
                self.changed_memory.add(addr)
                
            elif self.opcode == 'MOV':
                rd, imm = self.operands
                self.registers[rd] = int(imm)
                self.changed_registers.add(rd)
                
            elif self.opcode == 'JUMP':
                addr = self.operands[0]
                addr = int(addr, 16) if addr.startswith('0x') else int(addr)
                self.pc = addr - 1  # -1 because pc will increment after
                
            elif self.opcode == 'BEQ':
                rs1, rs2, addr = self.operands
                addr = int(addr, 16) if addr.startswith('0x') else int(addr)
                if self.registers[rs1] == self.registers[rs2]:
                    self.pc = addr - 1
                    
            elif self.opcode == 'NOP':
                pass
                
            elif self.opcode == 'HALT':
                self.halted = True
                return False
                
            else:
                raise ValueError(f"Unknown opcode: {self.opcode}")
                
            self.control_signals['writeback'] = True
            self.pc += 1
            return True
            
        except Exception as e:
            print(f"Error executing instruction: {e}")
            self.halted = True
            return False

class CPUSimulatorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # Configure Gemini
        genai.configure(api_key="AIzaSyCpupUAO4Tem3yC0Thep8-ZRuLDKQH18EI")  # Replace with your Gemini API key
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        self.cpu = CPU()
        self.running = False
        self.log_visible = False
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.step)
        self.active_colors = {
            'fetch': QColor(173, 216, 230),
            'decode': QColor(144, 238, 144),
            'execute': QColor(255, 182, 193),
            'memory': QColor(255, 255, 153),
            'writeback': QColor(221, 160, 221)
        }
        self.changed_color = QColor(255, 200, 150)
        self.current_instr_color = QColor(200, 230, 255)
        
    def init_ui(self):
        self.setWindowTitle('CPU Instruction Execution Simulator')
        self.setGeometry(100, 100, 1200, 800)  # Wider window for logs
        
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # Top row: Instruction viewer and register panel
        top_row = QHBoxLayout()
        main_layout.addLayout(top_row)
        
        # Instruction viewer
        instruction_group = QGroupBox("🧾 Instruction Viewer")
        instruction_layout = QVBoxLayout()
        
        self.instruction_text = QTextEdit()
        self.instruction_text.setReadOnly(True)
        self.instruction_text.setFixedHeight(200)
        self.instruction_text.setStyleSheet("font-family: monospace;")
        
        self.pc_spin = QSpinBox()
        self.pc_spin.setMinimum(0)
        self.pc_spin.setMaximum(99)
        self.pc_spin.valueChanged.connect(self.update_pc)
        
        instruction_layout.addWidget(QLabel("Program Counter (PC):"))
        instruction_layout.addWidget(self.pc_spin)
        instruction_layout.addWidget(QLabel("Instructions:"))
        instruction_layout.addWidget(self.instruction_text)
        instruction_group.setLayout(instruction_layout)
        top_row.addWidget(instruction_group)
        
        # Register panel
        register_group = QGroupBox("💾 Register Panel")
        register_layout = QVBoxLayout()
        
        self.register_table = QTableWidget()
        self.register_table.setColumnCount(2)
        self.register_table.setHorizontalHeaderLabels(["Register", "Value"])
        self.register_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.register_table.verticalHeader().setVisible(False)
        
        register_layout.addWidget(self.register_table)
        register_group.setLayout(register_layout)
        top_row.addWidget(register_group)
        
        # Middle row: ALU panel and control signals
        middle_row = QHBoxLayout()
        main_layout.addLayout(middle_row)
        
        # ALU panel
        alu_group = QGroupBox("🧮 ALU Panel")
        alu_layout = QVBoxLayout()
        
        self.alu_operation = QLabel("Operation: None")
        self.alu_input1 = QLabel("Input 1: -")
        self.alu_input2 = QLabel("Input 2: -")
        self.alu_output = QLabel("Output: -")
        
        alu_layout.addWidget(self.alu_operation)
        alu_layout.addWidget(self.alu_input1)
        alu_layout.addWidget(self.alu_input2)
        alu_layout.addWidget(self.alu_output)
        alu_group.setLayout(alu_layout)
        middle_row.addWidget(alu_group)
        
        # Control signals
        control_group = QGroupBox("📡 Control Signals")
        control_layout = QVBoxLayout()
        
        self.fetch_signal = QLabel("Fetch: OFF")
        self.decode_signal = QLabel("Decode: OFF")
        self.execute_signal = QLabel("Execute: OFF")
        self.memory_signal = QLabel("Memory: OFF")
        self.writeback_signal = QLabel("Writeback: OFF")
        
        for signal in [self.fetch_signal, self.decode_signal, self.execute_signal,
                      self.memory_signal, self.writeback_signal]:
            signal.setFixedWidth(150)
            signal.setAlignment(Qt.AlignCenter)
        
        control_layout.addWidget(self.fetch_signal)
        control_layout.addWidget(self.decode_signal)
        control_layout.addWidget(self.execute_signal)
        control_layout.addWidget(self.memory_signal)
        control_layout.addWidget(self.writeback_signal)
        control_group.setLayout(control_layout)
        middle_row.addWidget(control_group)
        
        # Bottom row: Memory panel and Logs panel (in a splitter)
        bottom_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(bottom_splitter)
        
        # Memory panel
        memory_group = QGroupBox("🧠 Memory Panel")
        memory_layout = QVBoxLayout()
        
        self.memory_table = QTableWidget()
        self.memory_table.setColumnCount(2)
        self.memory_table.setHorizontalHeaderLabels(["Address", "Value"])
        self.memory_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        memory_layout.addWidget(self.memory_table)
        memory_group.setLayout(memory_layout)
        
        # Logs panel (initially hidden)
        self.logs_group = QGroupBox("📜 Execution Logs")
        self.logs_layout = QVBoxLayout()
        
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setStyleSheet("font-family: monospace;")
        
        self.logs_layout.addWidget(self.logs_text)
        self.logs_group.setLayout(self.logs_layout)
        self.logs_group.setVisible(False)  # Hidden by default
        
        bottom_splitter.addWidget(memory_group)
        bottom_splitter.addWidget(self.logs_group)
        bottom_splitter.setSizes([400, 200])  # Initial sizes
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.step_button = QPushButton("▶ Step")
        self.step_button.clicked.connect(self.step)
        
        self.run_button = QPushButton("⏵ Run")
        self.run_button.clicked.connect(self.run)
        
        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.clicked.connect(self.pause)
        self.pause_button.setEnabled(False)
        
        self.reset_button = QPushButton("⏹ Reset")
        self.reset_button.clicked.connect(self.full_reset)  # Changed to full_reset
        
        self.load_button = QPushButton("📂 Load Program")
        self.load_button.clicked.connect(self.load_program)
        
        self.logs_button = QPushButton("📜 Show Logs")
        self.logs_button.setCheckable(True)
        self.logs_button.toggled.connect(self.toggle_logs)
        
        self.generate_button = QPushButton("✨ Generate Program")
        self.generate_button.clicked.connect(self.generate_program)
        
        button_layout.addWidget(self.step_button)
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.logs_button)
        button_layout.addWidget(self.generate_button)
        main_layout.addLayout(button_layout)
        self.setStyleSheet("""
        QMainWindow {
            background-color: #121212;
            font-family: "Segoe UI";
        }

        QLabel, QSpinBox, QTextEdit, QTableWidget, QPushButton, QGroupBox {
            font-size: 16px;
            color: #FFFFFF;
        }

        QGroupBox {
            background-color: #1E1E1E;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 3px;
            font-size: 18px;
            font-weight: bold;
            color: #4FC3F7;
        }

        QPushButton {
            background-color: #1976D2;
            color: white;
            padding: 6px;
        }

        QPushButton:hover {
            background-color: #2196F3;
        }

        QTextEdit, QTableWidget, QSpinBox {
            background-color: #1E1E1E;
        }

        QTableWidget::item {
            color: #EEEEEE;
        }

        QHeaderView::section {
            background-color: #333;
            color: #4FC3F7;
            padding: 4px;
            font-weight: bold;
        }
    """)


        self.update_display()
        
    def toggle_logs(self, checked):
        """Toggle visibility of the logs panel"""
        self.logs_group.setVisible(checked)
        self.log_visible = checked
        self.logs_button.setText("📜 Hide Logs" if checked else "📜 Show Logs")
        
    def add_log_entry(self, action, details):
        """Add a new entry to the execution log"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {action}: {details}\n"
        self.logs_text.moveCursor(self.logs_text.textCursor().End)
        self.logs_text.insertPlainText(log_entry)
        self.logs_text.ensureCursorVisible()
        
    def update_display(self):
        # Update instruction viewer with colored current instruction
        # Update instruction viewer
        self.instruction_text.clear()
        if not self.cpu.instructions:  # Handle empty program case
            self.instruction_text.setPlainText("No program loaded")
            return
            
        cursor = self.instruction_text.textCursor()
        format_normal = cursor.charFormat()
        
        for i, instr in enumerate(self.cpu.instructions):
            if i == self.cpu.pc:
                # Highlight current instruction
                format_current = cursor.charFormat()
                format_current.setBackground(self.current_instr_color)
                cursor.setCharFormat(format_current)
                cursor.insertText(f"> {i}: {instr}\n")
                cursor.setCharFormat(format_normal)
            else:
                cursor.insertText(f"  {i}: {instr}\n")
        
        self.pc_spin.setValue(self.cpu.pc)
        
        # Update register table with changed registers highlighted
        self.register_table.setRowCount(len(self.cpu.registers))
        for i, (reg, val) in enumerate(self.cpu.registers.items()):
            self.register_table.setItem(i, 0, QTableWidgetItem(reg))
            value_item = QTableWidgetItem(str(val))
            
            # Highlight changed registers
            if reg in self.cpu.changed_registers:
                value_item.setBackground(self.changed_color)
                self.register_table.setItem(i, 0, QTableWidgetItem(reg))
                self.register_table.item(i, 0).setBackground(self.changed_color)
                self.add_log_entry("Register Update", f"{reg} = {val}")
            
            self.register_table.setItem(i, 1, value_item)
        
        # Update ALU panel
        if hasattr(self.cpu, 'opcode'):
            self.alu_operation.setText(f"Operation: {self.cpu.opcode}")
            if len(self.cpu.operands) >= 2 and self.cpu.opcode in ['ADD', 'SUB']:
                self.alu_input1.setText(f"Input 1: {self.cpu.registers.get(self.cpu.operands[1], '?')}")
                self.alu_input2.setText(f"Input 2: {self.cpu.registers.get(self.cpu.operands[2], '?')}")
                self.alu_output.setText(f"Output: {self.cpu.alu_output}")
                self.add_log_entry("ALU Operation", 
                                 f"{self.cpu.opcode} {self.cpu.operands[1]} {self.cpu.operands[2]} → {self.cpu.alu_output}")
            else:
                self.alu_input1.setText("Input 1: -")
                self.alu_input2.setText("Input 2: -")
                self.alu_output.setText("Output: -")
        else:
            self.alu_operation.setText("Operation: None")
            self.alu_input1.setText("Input 1: -")
            self.alu_input2.setText("Input 2: -")
            self.alu_output.setText("Output: -")
        
        # Update control signals with colors
        self.update_signal_label(self.fetch_signal, 'fetch')
        self.update_signal_label(self.decode_signal, 'decode')
        self.update_signal_label(self.execute_signal, 'execute')
        self.update_signal_label(self.memory_signal, 'memory')
        self.update_signal_label(self.writeback_signal, 'writeback')
        
        # Log control signal changes
        for signal, active in self.cpu.control_signals.items():
            if active:
                self.add_log_entry("Control Signal", f"{signal.upper()} activated")
        
        # Update memory table with changed memory highlighted
        self.memory_table.setRowCount(len(self.cpu.memory))
        for i, (addr, val) in enumerate(self.cpu.memory.items()):
            addr_item = QTableWidgetItem(f"0x{addr:04x}")
            val_item = QTableWidgetItem(str(val))
            
            # Highlight changed memory locations
            if addr in self.cpu.changed_memory:
                addr_item.setBackground(self.changed_color)
                val_item.setBackground(self.changed_color)
                self.add_log_entry("Memory Update", f"0x{addr:04x} = {val}")
            
            self.memory_table.setItem(i, 0, addr_item)
            self.memory_table.setItem(i, 1, val_item)
        
        # Update button states
        self.step_button.setEnabled(not self.running and not self.cpu.halted)
        self.run_button.setEnabled(not self.running and not self.cpu.halted)
        self.pause_button.setEnabled(self.running)
        
    def update_signal_label(self, label, signal_name):
        if self.cpu.control_signals[signal_name]:
            label.setText(f"{signal_name.capitalize()}: ON")
            label.setStyleSheet(f"background-color: {self.active_colors[signal_name].name()};")
        else:
            label.setText(f"{signal_name.capitalize()}: OFF")
            label.setStyleSheet("background-color: none;")
        
    def step(self):
        if self.cpu.halted:
            self.add_log_entry("Execution", "Program halted")
            self.step_button.setEnabled(False)
            self.run_button.setEnabled(False)
            return
        
        
        if not hasattr(self.cpu, 'ir') or self.cpu.ir is None:
            self.add_log_entry("Pipeline Stage", "Fetching instruction")
            self.cpu.fetch()
            self.add_log_entry("Instruction Fetched", f"PC={self.cpu.pc}, IR='{self.cpu.ir}'")
        elif not hasattr(self.cpu, 'opcode'):
            self.add_log_entry("Pipeline Stage", "Decoding instruction")
            self.cpu.decode()
            self.add_log_entry("Instruction Decoded", 
                              f"Opcode={self.cpu.opcode}, Operands={self.cpu.operands}")
        else:
            self.add_log_entry("Pipeline Stage", "Executing instruction")
            result = self.cpu.execute()
            if result:
                self.add_log_entry("Execution Complete", f"PC now {self.cpu.pc}")
            else:
                self.add_log_entry("Execution Halted", "Program completed")
            if hasattr(self.cpu, 'opcode'):
                delattr(self.cpu, 'opcode')
            if hasattr(self.cpu, 'operands'):
                delattr(self.cpu, 'operands')
        self.add_log_entry("------------", "----------------")
        self.update_display()
        
    def run(self):
        self.running = True
        self.step_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.timer.start(500)  # 500ms between steps
        self.add_log_entry("Simulation", "Started continuous execution")
        
    def pause(self):
        self.running = False
        self.timer.stop()
        self.step_button.setEnabled(not self.cpu.halted)
        self.run_button.setEnabled(not self.cpu.halted)
        self.pause_button.setEnabled(False)
        self.add_log_entry("Simulation", "Paused execution")
        
    def reset(self):
        self.pause()
        self.cpu.reset()
        self.logs_text.clear()
        self.add_log_entry("Simulation", "System reset")
        self.update_display()
    
    
    
    def full_reset(self):
        """Complete reset including button states"""
        self.pause()
        self.cpu.reset()
        self.logs_text.clear()
        self.add_log_entry("System", "Full reset performed")
        self.update_display()
        # Ensure buttons are in correct state after reset
        self.step_button.setEnabled(True)
        self.run_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        
    
    
    def generate_program(self):
        """Generate a new compatible program using Gemini"""
        try:
            prompt = """Generate a short (3-10 line) assembly program for a CPU simulator with:
            - Instructions: ADD, SUB, MOV, LOAD, STORE, JUMP, BEQ, NOP, HALT
            - Registers: R0-R7
            - Memory: 0x000-0x0FF
            - Output JUST the instructions, no markdown code blocks, no line numbers
            - Program can be simple operations or little big but within range of 10 lines
            - Example:
            MOV R1 5
            ADD R2 R1 R1
            HALT"""
            
            response = self.model.generate_content(prompt)
            program_text = response.text
            
            # Remove markdown code blocks if present
            if program_text.startswith('```') and program_text.endswith('```'):
                program_text = program_text[3:-3]  # Remove triple backticks
                program_text = program_text.replace('assembly', '')  # Remove language specifier
            
            # Process into clean instructions
            instructions = []
            for line in program_text.split('\n'):
                line = line.strip()
                # Remove line numbers if present (e.g., "1: MOV" → "MOV")
                if ':' in line and line.split(':')[0].strip().isdigit():
                    line = line.split(':', 1)[1].strip()
                if line and not line.startswith('#'):
                    instructions.append(line.split('#')[0].strip())
            
            if not instructions:
                raise ValueError("No valid instructions generated")
                
        except Exception as e:
            self.add_log_entry("Generation Error", f"Gemini failed: {str(e)}")
            QMessageBox.warning(self, "Generation Failed", 
                            "Using fallback program generator\nError: " + str(e))
            instructions = self.generate_fallback_program()
        
        # Reset and load new program
        self.full_reset()
        self.cpu.load_program(instructions)
        self.add_log_entry("Program Generated", f"Loaded {len(instructions)} instructions")
        self.update_display()
        
        
    def load_program(self, program):
        self.instructions = program
        self.pc = 0
        self.ir = None  # Clear any previous instruction
        if hasattr(self, 'opcode'):
            delattr(self, 'opcode')
        if hasattr(self, 'operands'):
            delattr(self, 'operands')
        self.halted = False
        self.changed_registers.clear()
        self.changed_memory.clear()
            
    def update_pc(self, value):
        if 0 <= value < len(self.cpu.instructions):
            self.cpu.pc = value
            self.cpu.ir = None
            if hasattr(self.cpu, 'opcode'):
                delattr(self.cpu, 'opcode')
            if hasattr(self.cpu, 'operands'):
                delattr(self.cpu, 'operands')
            self.add_log_entry("Manual PC Update", f"Set PC to {value}")
            self.update_display()

def main():
    app = QApplication(sys.argv)
    simulator = CPUSimulatorGUI()
    
    # Load sample program
    sample_program = [
        "MOV R1 10",
        "MOV R2 20",
        "ADD R3 R1 R2",
        "STORE R3 0x100",
        "LOAD R4 0x100",
        "SUB R5 R4 R1",
        "BEQ R5 R2 8",
        "MOV R6 99",
        "HALT",
        "MOV R6 42"
    ]
    simulator.cpu.load_program(sample_program)
    simulator.update_display()  # Explicitly update display after loading
    
    simulator.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()