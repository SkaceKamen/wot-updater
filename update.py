from __future__ import print_function
import requests
import xml.etree.ElementTree as et
import os
import re
import subprocess
import sys
from utils import Unpacker
import argparse

def percent_fmt(num, total):
	return str(round((num * 100) / total)) + " %"

def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)

class Updater(object):
	versions = {}
	wotPath = None
	reporter = None
	host = None
	cleanPatches = False

	def __init__(self, wot_path='.', reporter=None, host=None, cleanPatches=False):
		self.wotPath = wot_path
		self.host = host
		self.cleanPatches = cleanPatches
		
		if reporter == None: reporter = VoidReporter()
		self.reporter = reporter

	def start(self):
		# Load current versions, if any
		launcher_config = os.path.join(self.wotPath, "WOTLauncher.cfg")
		self.versions = self.loadVersions(launcher_config)
		self.reporter.versionsLoaded(self, self.versions)

		# Make sure patch folders exists
		if not os.path.exists(os.path.join(self.wotPath, "Updates")):
			os.mkdir(os.path.join(self.wotPath, "Updates"))

		if not os.path.exists(os.path.join(self.wotPath, "UpdatesData")):
			os.mkdir(os.path.join(self.wotPath, "UpdatesData"))

		# Load patches
		patches = self.loadPatches(self.host)
		self.reporter.patchesLoaded(self, patches)

		if len(patches) == 0:
			return

		# Download patches if needed
		downloaded = 0
		for patch in patches:
			if not patch.exists(self.wotPath):
				patch.download(self.wotPath)
			
			downloaded += 1
			self.reporter.patchesDownloadProgress(self, downloaded, len(patches))

		# Apply downloaded patches
		applied = 0
		for patch in patches:
			patch.apply(self.wotPath)

			applied += 1
			self.reporter.patchesApplyProgress(self, applied, len(patches))

		# Save versions
		if not os.path.exists(launcher_config):
			root = et.Element('info')
			
			# Save versions
			for target in ["client","sdcontent","locale"]:
				sub = et.SubElement(root, target + "_ver")
				sub.text = self.versions[target]

			# Save used host
			pinfo = et.SubElement(root, "patch_info_urls")
			item = et.SubElement(pinfo, "item")
			item.text = self.host

			et.ElementTree(root).write(launcher_config)
		else:
			root = None
			with open(launcher_config, 'r') as f:
				root = et.fromstring(f.read())
			
			for target in ["client","sdcontent","locale"]:
				root.find(target + '_ver').text = self.versions[target]

			et.ElementTree(root).write(launcher_config)

	def loadVersions(self, file=None):
		versions = {
			'sdcontent': None,
			'client': None,
			'locale': None
		}

		if file != None and os.path.exists(file):
			with open(file, 'r') as f:
				root = et.fromstring(f.read())
				versions['sdcontent'] = root.find('sdcontent_ver').text
				versions['client'] = root.find('client_ver').text
				versions['locale'] = root.find('locale_ver').text

				host = root.find('patch_info_urls')
				if host is not None:
					host = host.find('item')
					if host is not None:
						host = host.text
		
		if self.host is None:
			self.reporter.warning("No host config found, using update.worldoftanks.eu")
			self.host = "update.worldoftanks.eu"

		return versions

	def loadPatches(self, host):
		patches = []
		
		for target in ["client","sdcontent","locale"]:
			r = requests.get(
				"http://%s/?target=%s&sdcontent_ver=%s&client_ver=%s&locale_ver=%s&lang=%s" % (
					host, target, self.versions["sdcontent"], self.versions["client"], self.versions["locale"], "en"
				)
			)

			root = et.fromstring(r.text)
			content = root.find('content')
			if content is not None:
				for child in root.find('content'):
					patches.append(Patch(self, child))
			
				self.versions[target] = root.find('version_to').text

		return patches

class Patch(object):
	def __init__(self, updater, element):
		self.updater = updater
		self.element = element
		self.name = element.find('name').text
		self.size = int(element.find('size').text)
		self.crc = element.find('crc').text
		self.mirrors = [ item.text for item in element.findall('http') ]
	
	def exists(self, wot_path):
		return os.path.exists(self.getFilename(wot_path))

	def getFilename(self, wot_path):
		return os.path.join(wot_path, "Updates", self.name)

	def download(self, wot_path, progress_size=1024*1024):
		r = requests.get(self.mirrors[0], stream=True)

		total_size = int(r.headers.get('content-length', 0))
		downloaded = 0

		with open(self.getFilename(wot_path), 'wb') as f:
			for data in r.iter_content(chunk_size=progress_size):
				downloaded += len(data)
				f.write(data)

				self.updater.reporter.patchDownloadProgress(self.updater, self, downloaded, total_size)

	def unpackProgress(self, done, current_file):
		self.updater.reporter.patchUnpackProgress(self.updater, self, done, len(self.files))

	def apply(self, wot_path, progress_callback = None, progress_size=5):
		# Make sure we have absolut path to WoT
		wot_path = os.path.abspath(wot_path)
		
		# Path where preupdated data are stored when working
		updates_path = os.path.join(wot_path, "UpdatesData")

		# If it's part of patch, updack only first part
		match = re.match(r'(.*)\.([0-9]{3})$$', self.name)
		if match:
			filename = match.group(1)
			number = int(match.group(2).lstrip('0'))
			if number != 1:
				return
		
		# Load files info
		self.files = Unpacker.getFiles(self.getFilename(wot_path))
		
		# Unpack package
		self.unpackProgress(0, None)
		Unpacker.unpackFiles(self.getFilename(wot_path), os.path.join(wot_path, "UpdatesData"), self.unpackProgress)

		# Now apply the patch data
		applied = 0
		for root, dirs, files in os.walk(updates_path):
			for filename in files:
				# Path relative to WoT root
				relative_path = os.path.abspath(root)[len(os.path.abspath(updates_path)) + 1:]
				
				# Service.xml contains additional operations, like deleting files
				# Apply service changes and don't copy it to target path
				if relative_path == "_service" and filename == "service.xml":
					self.applyService(wot_path, os.path.join(root, filename))
					os.remove(os.path.join(root, filename))
					continue

				# Make sure target path exists
				if not os.path.exists(os.path.join(wot_path, relative_path)):
					os.makedirs(os.path.join(wot_path, relative_path))

				# rdiff and xdiff are patch files, which need to be handled using appropriate tools
				match = re.match(r'(.*\.pkg).*\.(rdiff|xdiff)$', filename)
				if match:
					# Filename inside WoT path
					filename_based = os.path.join(relative_path, match.group(1))

					# Patch will be applied and new file created
					original_file = os.path.join(wot_path, filename_based)
					patch_file = os.path.join(root, filename)
					updated_file = os.path.join(wot_path, filename_based + ".updated")

					if match.group(2) == "rdiff":
						subprocess.check_call([
							"rdiff", "patch",
							original_file,
							patch_file,
							updated_file
						])
					
					if match.group(2) == "xdiff":
						subprocess.check_call([
							"xdelta3", "-d", "-s",
							original_file,
							patch_file,
							updated_file
						])

					# Remove patch and old file
					os.remove(patch_file)
					os.remove(original_file)

					# Move new file to wot root
					os.rename(updated_file, original_file)
				else:
					filename_based = os.path.join(relative_path, filename)
					updated_file = os.path.join(root, filename)
					original_file = os.path.join(wot_path, filename_based)

					if os.path.exists(original_file):
						os.remove(original_file)
					
					os.rename(updated_file, original_file)
				
				applied += 1
				self.updater.reporter.patchApplyProgress(self.updater, self, applied, len(self.files))
		
		# Remove patch file if required
		if self.updater.cleanPatches:
			os.remove(self.getFilename(wot_path))

	def applyService(self, wot_root, path):
		root = et.parse(path).getroot()
		for item in root.find("files_to_delete").findall("file"):
			filename = os.path.join(wot_root, item.text)
			if os.path.exists(filename):
				os.remove(filename)

class VoidReporter(object):
	def warning(self, text): pass
	def versionsLoaded(self, updater): pass
	def patchesLoaded(self, updater, patches): pass
	def patchesDownloadProgress(self, updater, done, total): pass
	def patchesApplyProgress(self, updater, done, total): pass
	def patchDownloadProgress(self, updater, patch, downloaded, size): pass
	def patchUnpackProgress(self, updater, patch, unpacked, total): pass
	def patchApplyProgress(self, updater, patch, applied, total): pass

class ConsoleReporter(object):
	previous = None

	def print(self, text, clear=True, end='\n'):
		if clear and self.previous is not None and len(self.previous) > len(text):
			text += " " * (len(self.previous) - len(text))
		self.previous = text

		print(text, end=end)
		sys.stdout.flush()
	
	def warning(self, text):
		self.print("Warning: %s" % text)

	def versionsLoaded(self, updater, versions):
		self.versions = versions.copy()
	
	def patchesLoaded(self, updater, patches):
		if len(patches) > 0:
			for key, value in updater.versions.items():
				if self.versions[key] != value:
					self.print("%s: %s -> %s" % (key, self.versions[key], value))
			
			self.print("%d patches required (%s)" % (len(patches), sizeof_fmt(sum([ patch.size for patch in patches ]))))
		else:
			self.print("Version up to date")

	def patchesDownloadProgress(self, updater, done, total):
		self.print("\rDownloaded %d / %d patches (%s)" % (done, total, percent_fmt(done, total)))

	def patchesApplyProgress(self, updater, done, total):
		self.print("\rApplied %d / %d patches (%s)" % (done, total, percent_fmt(done, total)))

	def patchDownloadProgress(self, updater, patch, downloaded, total):
		self.print("\rDownloading %s: %s / %s (%s)" % (patch.name, sizeof_fmt(downloaded), sizeof_fmt(total), percent_fmt(downloaded, total)), end='')

	def patchUnpackProgress(self, updater, patch, unpacked, total):
		self.print("\rUnpacking %s: %s / %s (%s)" % (patch.name, unpacked, total, percent_fmt(unpacked, total)), end='')

	def patchApplyProgress(self, updater, patch, applied, total):
		self.print("\rApplying %s: %s / %s (%s)" % (patch.name, applied, total, percent_fmt(applied, total)), end='')

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Updates World of Tanks installation from specified source')
	parser.add_argument('-p', '--path', dest='path', help='path to world of tanks installation (default .)', default='.')
	parser.add_argument('-u', '--host', dest='host', help='update host (default loaded from installation path)')
	parser.add_argument('-q', '--quiet', dest='quiet', help='suppress output', action='store_true')

	args = parser.parse_args()

	# Validate options
	if not os.path.exists(args.path):
		print("Invalid World of Tanks path")
		sys.exit(1)

	reporter = VoidReporter()
	if not args.quiet:
		reporter = ConsoleReporter()

	# Start updater
	updater = Updater(args.path, reporter, args.host)
	updater.start()
