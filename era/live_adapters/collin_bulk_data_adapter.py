"""CCS-001: read-only, memory-bounded Collin AD_Public acquisition."""

import base64
import json
import os
import re
from pathlib import Path
import subprocess

from era.acquisition.profiles.collin_profile import (
    CODE_SHEETS,
    COLLIN_PROFILE,
    SOURCE_COLUMNS,
    map_collin_row,
)
from era.providers.provider_models import ProviderEvidence
from era.providers import provider_errors
from era.shared.audit import BaseAuditPublisher


ACCESS_DRIVER_MISSING = "ACCESS_DRIVER_MISSING"
ACCESS_SOURCE_MISSING = "ACCESS_SOURCE_MISSING"
ACCESS_TABLE_MISSING = "ACCESS_TABLE_MISSING"
ACCESS_QUERY_FAILED = "ACCESS_QUERY_FAILED"
COLLIN_RECORD_NOT_FOUND = "COLLIN_RECORD_NOT_FOUND"
COLLIN_RECORD_AMBIGUOUS = "COLLIN_RECORD_AMBIGUOUS"
CODE_LIST_SOURCE_MISSING = "CODE_LIST_SOURCE_MISSING"
COLLIN_ADDRESS_NOT_FOUND = "COLLIN_ADDRESS_NOT_FOUND"
COLLIN_ADDRESS_AMBIGUOUS = "COLLIN_ADDRESS_AMBIGUOUS"

_ADDRESS_TOKENS = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "ROAD": "RD",
    "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR",
    "PARKWAY": "PKWY", "HIGHWAY": "HWY", "PLACE": "PL", "TERRACE": "TER",
    "APARTMENT": "UNIT", "APT": "UNIT", "SUITE": "UNIT", "STE": "UNIT",
}


def normalize_collin_address(value):
    """Deterministic acquisition normalization; never performs geocoding."""
    text = str(value or "").upper().replace("#", " UNIT ")
    text = re.sub(r"(?<=\d)[- ](?=\d{4}\b)", "", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    tokens = []
    for token in text.split():
        token = _ADDRESS_TOKENS.get(token, token)
        if token.isdigit() and len(token) == 9:
            token = token[:5]
        tokens.append(token)
    return " ".join(tokens)


def _encoded_command(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


class CollinBulkDataAdapter:
    CONNECTOR_ID = COLLIN_PROFILE.provider_id
    PROVIDER_NAME = "Collin Central Appraisal District"
    SOURCE_NAME = COLLIN_PROFILE.source_name
    LEGAL_BASIS = "PUBLIC_RECORD"
    TABLE_NAME = "AD_Public"
    EXPECTED_ROW_COUNT = 503_711

    def __init__(self, mdb_path, code_list_path, audit=None, version="2026-preliminary"):
        self._mdb_path = str(Path(mdb_path))
        self._code_list_path = str(Path(code_list_path))
        self._version = version
        self.audit = audit or BaseAuditPublisher()
        self.last_warnings = ()
        self._code_lists = None
        # AX-ADAPT-001: exact subprocess stdout bytes for the last row query.
        self._last_raw_query_bytes = None

    def provider_id(self):
        return self.CONNECTOR_ID

    def provider_name(self):
        return self.PROVIDER_NAME

    def connector_version(self):
        return self._version

    @staticmethod
    def _powershell32():
        path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        return str(path)

    def _run_script(self, script, extra_env=None):
        return self._run_script_bytes(script, extra_env).decode("utf-8", errors="replace").strip()

    def _run_script_bytes(self, script, extra_env=None):
        powershell = self._powershell32()
        if not Path(powershell).exists():
            raise RuntimeError(ACCESS_DRIVER_MISSING)
        env = os.environ.copy()
        env.update(extra_env or {})
        completed = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", _encoded_command(script)],
            capture_output=True,
            text=False,
            env=env,
            timeout=120,
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip()
            if "not registered" in message:
                raise RuntimeError(ACCESS_DRIVER_MISSING)
            if "AD_Public" in message and ("find" in message.lower() or "exist" in message.lower()):
                raise RuntimeError(ACCESS_TABLE_MISSING)
            raise RuntimeError(f"{ACCESS_QUERY_FAILED}: {message}")
        return bytes(completed.stdout).strip()

    def _query_rows(self, lookup):
        if not Path(self._mdb_path).is_file():
            raise RuntimeError(ACCESS_SOURCE_MISSING)
        numeric = str(lookup).isdigit()
        script = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$connection = New-Object System.Data.OleDb.OleDbConnection("Provider=Microsoft.Jet.OLEDB.4.0;Data Source=$env:ERA_MDB_PATH;Mode=Read;")
$connection.Open()
try {
    $columns = $env:ERA_COLUMNS
    $field = if ($env:ERA_LOOKUP_NUMERIC -eq '1') { 'prop_id' } else { 'geo_id' }
    $command = $connection.CreateCommand()
    $command.CommandText = "SELECT TOP 2 $columns FROM AD_Public WHERE $field = ?"
    if ($field -eq 'prop_id') { [void]$command.Parameters.AddWithValue('@p1', [int]$env:ERA_LOOKUP) }
    else { [void]$command.Parameters.AddWithValue('@p1', $env:ERA_LOOKUP) }
    $reader = $command.ExecuteReader()
    $rows = @()
    while ($reader.Read()) {
        $record = [ordered]@{}
        for ($i = 0; $i -lt $reader.FieldCount; $i++) {
            $record[$reader.GetName($i)] = if ($reader.IsDBNull($i)) { $null } else { $reader.GetValue($i) }
        }
        $rows += [pscustomobject]$record
    }
    $reader.Close()
    ConvertTo-Json -InputObject @($rows) -Compress -Depth 4
}
finally { $connection.Close() }
'''
        raw_output = self._run_script_bytes(script, {
            "ERA_MDB_PATH": self._mdb_path,
            "ERA_COLUMNS": ",".join(f"[{column}]" for column in SOURCE_COLUMNS),
            "ERA_LOOKUP": str(lookup),
            "ERA_LOOKUP_NUMERIC": "1" if numeric else "0",
        })
        self._last_raw_query_bytes = raw_output
        output = raw_output.decode("utf-8", errors="replace")
        return json.loads(output or "[]")

    def _query_address_candidates(self, street_number):
        if not Path(self._mdb_path).is_file():
            raise RuntimeError(ACCESS_SOURCE_MISSING)
        script = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$connection = New-Object System.Data.OleDb.OleDbConnection("Provider=Microsoft.Jet.OLEDB.4.0;Data Source=$env:ERA_MDB_PATH;Mode=Read;")
$connection.Open()
try {
    $command = $connection.CreateCommand()
    $command.CommandText = "SELECT prop_id, situs_display FROM AD_Public WHERE Left(Trim(situs_display), ?) = ?"
    [void]$command.Parameters.AddWithValue('@p1', $env:ERA_STREET_NUMBER.Length)
    [void]$command.Parameters.AddWithValue('@p2', $env:ERA_STREET_NUMBER)
    $reader = $command.ExecuteReader()
    $rows = @()
    while ($reader.Read()) {
        $rows += [pscustomobject][ordered]@{
            prop_id = if ($reader.IsDBNull(0)) { $null } else { $reader.GetValue(0) }
            situs_display = if ($reader.IsDBNull(1)) { $null } else { $reader.GetValue(1) }
        }
    }
    $reader.Close()
    ConvertTo-Json -InputObject @($rows) -Compress -Depth 3
}
finally { $connection.Close() }
'''
        output = self._run_script(script, {
            "ERA_MDB_PATH": self._mdb_path,
            "ERA_STREET_NUMBER": street_number,
        })
        return json.loads(output or "[]")

    def resolve_address(self, address):
        normalized = normalize_collin_address(address)
        first = normalized.split(" ", 1)[0] if normalized else ""
        if not first.isdigit():
            return COLLIN_ADDRESS_NOT_FOUND, None, 0
        rows = self._query_address_candidates(first)
        matches = [row for row in rows if normalize_collin_address(row.get("situs_display")) == normalized]
        if not matches:
            return COLLIN_ADDRESS_NOT_FOUND, None, 0
        if len(matches) != 1:
            return COLLIN_ADDRESS_AMBIGUOUS, None, len(matches)
        return provider_errors.PASS, str(matches[0]["prop_id"]), 1

    def _load_code_lists(self):
        if self._code_lists is not None:
            return self._code_lists
        if not Path(self._code_list_path).is_file():
            raise RuntimeError(CODE_LIST_SOURCE_MISSING)
        script = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$connection = New-Object System.Data.OleDb.OleDbConnection("Provider=Microsoft.Jet.OLEDB.4.0;Data Source=$env:ERA_XLS_PATH;Extended Properties='Excel 8.0;HDR=YES;IMEX=1';Mode=Read;")
$connection.Open()
try {
    $result = [ordered]@{}
    foreach ($sheet in ($env:ERA_CODE_SHEETS | ConvertFrom-Json)) {
        $command = $connection.CreateCommand()
        $command.CommandText = "SELECT Code, Name FROM [$sheet`$]"
        $reader = $command.ExecuteReader()
        $codes = [ordered]@{}
        while ($reader.Read()) {
            if (-not $reader.IsDBNull(0)) {
                $code = ([string]$reader.GetValue(0)).Trim().ToUpperInvariant()
                $name = if ($reader.IsDBNull(1)) { '' } else { ([string]$reader.GetValue(1)).Trim() }
                if ($code) { $codes[$code] = $name }
            }
        }
        $reader.Close()
        $result[$sheet] = $codes
    }
    ConvertTo-Json -InputObject $result -Compress -Depth 5
}
finally { $connection.Close() }
'''
        output = self._run_script(script, {
            "ERA_XLS_PATH": self._code_list_path,
            "ERA_CODE_SHEETS": json.dumps(sorted(set(CODE_SHEETS.values()))),
        })
        self._code_lists = json.loads(output)
        return self._code_lists

    def source_row_count(self):
        script = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$connection = New-Object System.Data.OleDb.OleDbConnection("Provider=Microsoft.Jet.OLEDB.4.0;Data Source=$env:ERA_MDB_PATH;Mode=Read;")
$connection.Open()
try {
    $command = $connection.CreateCommand()
    $command.CommandText = 'SELECT COUNT(*) FROM AD_Public'
    Write-Output $command.ExecuteScalar()
}
finally { $connection.Close() }
'''
        return int(self._run_script(script, {"ERA_MDB_PATH": self._mdb_path}))

    def health_check(self):
        try:
            rows = self._query_rows("-1")
            return isinstance(rows, list)
        except RuntimeError as exc:
            self.audit.publish("COLLIN_HEALTH_FAILED", {"reason": str(exc)})
            return False

    def retrieve(self, property_id):
        try:
            rows = self._query_rows(property_id)
            if not rows:
                return COLLIN_RECORD_NOT_FOUND, {}
            if len(rows) != 1:
                return COLLIN_RECORD_AMBIGUOUS, {}
            evidence_map, warnings = map_collin_row(rows[0], self._load_code_lists())
        except RuntimeError as exc:
            reason = str(exc).split(":", 1)[0]
            self.audit.publish("COLLIN_RETRIEVE_FAILED", {"reason": str(exc), "property_id": property_id})
            return reason, {}

        self.last_warnings = warnings
        for warning in warnings:
            self.audit.publish("COLLIN_CODE_WARNING", {"warning": warning, "property_id": property_id})
        evidence = [
            ProviderEvidence(field_name=field, raw_value=value)
            for field, value in sorted(evidence_map.items())
            if value not in (None, "")
        ]
        return provider_errors.PASS, {
            "evidence": evidence,
            "provenance": {"legal_basis": self.LEGAL_BASIS},
            "source_reference": f"{self.SOURCE_NAME}:{rows[0]['prop_id']}",
        }
