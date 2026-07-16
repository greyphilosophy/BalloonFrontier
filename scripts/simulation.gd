extends Node
## Balloon simulation engine.
##
## Implements the fixed-step vertical balloon simulation.
## Deterministic physics with configurable parameters.
## Reference: GDD Sections 6.1-6.6.

const DT: float = 0.1
const R_AIR: float = 287.05
const G: float = 9.80665
const R_UNIVERSAL: float = 8.314462618

const SEA_LEVEL_PRESSURE: float = 101325.0
const SEA_LEVEL_TEMPERATURE: float = 288.15

const MOLAR_MASS: Dictionary = {
    "helium": 0.0040026,
    "hydrogen": 0.002016,
    "hot_air": 0.02897,
    "methane": 0.01604,
}

var _altitude_m: float = 0.0
var _velocity_mps: float = 0.0
var _gas_mass_kg: float = 1.0
var _gas_type: String = "helium"
var _gas_temperature_k: float = 288.15
var _payload_mass_kg: float = 10.0
var _drag_coefficient: float = 0.47
var _envelope_max_volume_m3: float = 10.0
var _envelope_stretch_ratio: float = 2.5
var _burst: bool = false
var _time_s: float = 0.0

# Telemetry
var _telemetry: Array = []

signal telemetry_updated
signal burst_signal


func _physics_process(delta: float):
    # Fixed-step integration
    var step: float = DT
    _altitude_m += _velocity_mps * step
    _velocity_mps += _net_acceleration() * step
    _time_s += step

    # Check for burst
    var vol: float = _gas_volume()
    var burst_vol: float = _envelope_max_volume_m3 * _envelope_stretch_ratio
    if vol >= burst_vol:
        _burst = true
        emit_signal("burst_signal")

    _telemetry.append({
        "time": _time_s,
        "altitude": _altitude_m,
        "velocity": _velocity_mps,
        "volume": vol,
        "pressure": _pressure(),
        "net_lift": _buoyant_force(),
    })
    emit_signal("telemetry_updated")


func _net_acceleration():
    var F_buoy: float = _buoyant_force()
    var F_weight: float = (_gas_mass_kg + _payload_mass_kg) * G
    var F_drag: float = _drag()
    return (F_buoy - F_weight - F_drag) / (_gas_mass_kg + _payload_mass_kg)


func _buoyant_force():
    var rho_air: float = _density()
    var rho_gas: float = _gas_density()
    return (rho_air - rho_gas) * G * _gas_volume()


func _drag():
    var rho: float = _density()
    return 0.5 * rho * (_velocity_mps * _velocity_mps) * _drag_coefficient * _spherical_area()


func _gas_volume():
    var n: float = _gas_mass_kg / MOLAR_MASS[_gas_type]
    return n * R_UNIVERSAL * _gas_temperature_k / _pressure()


func _gas_density():
    return _pressure() / ((R_UNIVERSAL / MOLAR_MASS[_gas_type]) * _gas_temperature_k)


func _pressure():
    # US Standard Atmosphere
    if _altitude_m <= 11000:
        var T: float = 288.15 - 0.0065 * _altitude_m
        return SEA_LEVEL_PRESSURE * pow(T / 288.15, -G / (R_AIR * (-0.0065)))
    elif _altitude_m <= 20000:
        var delta: float = _altitude_m - 11000
        return 22632.0 * exp(-G * delta / (R_AIR * 216.65))
    elif _altitude_m <= 50000:
        var T: float = 216.65 + 0.001 * (_altitude_m - 20000)
        return 5401.0 * pow(T / 216.65, -G / (R_AIR * 0.001))
    return 868.0


func _density():
    return _pressure() / (R_AIR * _get_temperature())


func _get_temperature():
    if _altitude_m <= 11000:
        return 288.15 - 0.0065 * _altitude_m
    elif _altitude_m <= 20000:
        return 216.65
    elif _altitude_m <= 50000:
        return 216.65 + 0.001 * (_altitude_m - 20000)
    return 270.0


func _spherical_area():
    var vol: float = _gas_volume()
    var r: float = pow(3.0 * vol / (4.0 * PI), 1.0/3.0)
    return PI * r * r


func set_gas_mass(mass_kg: float):
    _gas_mass_kg = mass_kg


func set_payload_mass(mass_kg: float):
    _payload_mass_kg = mass_kg


func set_gas_type(type: String):
    _gas_type = type


func set_drag_coefficient(cd: float):
    _drag_coefficient = cd


func get_altitude():
    return _altitude_m


func get_velocity():
    return _velocity_mps


func get_volume():
    return _gas_volume()


func is_burst():
    return _burst


func get_telemetry():
    return _telemetry


func reset():
    _altitude_m = 0.0
    _velocity_mps = 0.0
    _burst = false
    _time_s = 0.0
    _telemetry.clear()
