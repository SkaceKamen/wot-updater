import subprocess
import re

class Unpacker(object):
	@staticmethod
	def unpackFiles(filename, output_path, callback=None):
		process = subprocess.Popen(["7z", "x", "-y", "-o" + output_path, filename], stdout=subprocess.PIPE, universal_newlines=True)
		previous = None
		extracted = 0
		
		while True:
			line = process.stdout.readline()
			if not line: break

			match = re.match(r'Extracting\s*(.*)', line)
			if match:
				if previous != None:
					extracted += 1
					if callback != None: callback(extracted, previous)
				previous = match.group(1)

		extracted += 1
		if callback != None: callback(extracted, None)
	
	@staticmethod
	def getFiles(filename):
		output = subprocess.check_output(["7z", "l", filename])
		output = output.replace("\r", "").split("\n")
		
		files = []
		inside = False
		for line in output:
			if inside:
				match = re.match(r'((?:[0-9]{2,4}-){2}[0-9]+\s(?:[0-9]{0,2}:){2}[0-9]+)\s\.*([^\.])\.*\s*([0-9]+)\s*([0-9]+)\s*(.*)', line)
				if match:
					if match.group(2) == 'A':
						files.append({
							'date': match.group(1),
							'size': match.group(3),
							'compressed': match.group(4),
							'name': match.group(5)
						})

			elif "------" in line:
				inside = True

		return files