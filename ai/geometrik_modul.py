"""
PFN AP grafisinden klinik parametre hesabı (v2)

- Baumgaertner TAD-AP: APEX = anatomic_neck_axis extension
- NSA: Neck-Shaft Angle
- Cleveland: 9 zone
- Parker AP: vida-femur eksen kesisimi
"""
import numpy as np
import math


def euclidean_distance(p1, p2):
    return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def calculate_line_angle(line_a, line_b):
    v1 = np.array([line_a[1][0] - line_a[0][0], line_a[1][1] - line_a[0][1]])
    v2 = np.array([line_b[1][0] - line_b[0][0], line_b[1][1] - line_b[0][1]])
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle = math.degrees(math.acos(cos_angle))
    return angle if angle <= 180 else 360 - angle


def line_line_intersection(p1, p2, p3, p4):
    """Iki cizginin kesisim noktasi"""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    x = x1 + t * (x2 - x1)
    y = y1 + t * (y2 - y1)
    return (float(x), float(y))


def compute_femur_head_geometry(keypoints):
    center = np.array(keypoints['head_center'])
    d_vertical = euclidean_distance(keypoints['head_superior'], keypoints['head_inferior'])
    d_horizontal = euclidean_distance(keypoints['head_medial'], keypoints['head_lateral'])
    diameter_pixel = (d_vertical + d_horizontal) / 2
    radius = diameter_pixel / 2
    return center, radius, diameter_pixel


def compute_apex_baumgaertner(keypoints):
    """
    APEX: Femur boyun aksi uzantisinda femur basi yuzeyi.
    
    1. Boyun aksi yonu = (head_center - neck_distal) / |...|
    2. APEX = head_center + radius * axis_unit
    3. X_ap = ||APEX - screw_tip||
    """
    screw_tip = np.array(keypoints['screw_tip'])
    head_center = np.array(keypoints['head_center'])
    neck_distal = np.array(keypoints['neck_distal'])
    
    center, radius, diameter_pixel = compute_femur_head_geometry(keypoints)
    
    neck_axis = head_center - neck_distal
    axis_length = np.linalg.norm(neck_axis)
    
    if axis_length < 1e-6:
        x_ap = float(np.linalg.norm(screw_tip - head_center))
        return (float(head_center[0]), float(head_center[1])), x_ap, diameter_pixel, 'fallback_center'
    
    axis_unit = neck_axis / axis_length
    apex = head_center + radius * axis_unit
    x_ap_pixel = float(np.linalg.norm(screw_tip - apex))
    
    return (float(apex[0]), float(apex[1])), x_ap_pixel, diameter_pixel, 'anatomic_neck_axis'


def compute_pfn_parameters(keypoints, pixel_spacing_mm=0.14, D_true_mm=45.0, manual_apex=None):
    """
    PFN AP grafisinden tum klinik parametreler.
    
    manual_apex: kullanici elle yerlestirdiyse [x,y], yoksa None
    """
    kp = keypoints
    
    # APEX hesabi
    if manual_apex is not None and len(manual_apex) == 2:
        apex = (float(manual_apex[0]), float(manual_apex[1]))
        screw_tip = np.array(kp['screw_tip'])
        apex_arr = np.array(apex)
        x_ap_pixel = float(np.linalg.norm(screw_tip - apex_arr))
        _, _, d_ap_pixel = compute_femur_head_geometry(kp)
        method = 'manual'
    else:
        apex, x_ap_pixel, d_ap_pixel, method = compute_apex_baumgaertner(kp)
    
    # TAD-AP
    tad_ap_pixel_based = x_ap_pixel * pixel_spacing_mm
    if d_ap_pixel > 0:
        tad_ap_baumgaertner = (x_ap_pixel / d_ap_pixel) * D_true_mm
    else:
        tad_ap_baumgaertner = 0
    tad_ap_final = tad_ap_baumgaertner
    d_ap_measured_mm = d_ap_pixel * pixel_spacing_mm
    
    # NSA
    neck_line = (kp['head_center'], kp['neck_distal'])
    shaft_line = (kp['shaft_proximal'], kp['shaft_distal'])
    nsa = calculate_line_angle(neck_line, shaft_line)
    if nsa < 90:
        nsa = 180 - nsa
    
    # Cleveland Zon
    lateral_to_medial_x = kp['head_medial'][0] - kp['head_lateral'][0]
    if abs(lateral_to_medial_x) > 1:
        x_ratio = (kp['screw_tip'][0] - kp['head_lateral'][0]) / lateral_to_medial_x
    else:
        x_ratio = 0.5
    
    if x_ratio < 0.33:
        x_zone = 'lateral'
    elif x_ratio < 0.67:
        x_zone = 'central'
    else:
        x_zone = 'medial'
    
    sup_to_inf_y = kp['head_inferior'][1] - kp['head_superior'][1]
    if abs(sup_to_inf_y) > 1:
        y_ratio = (kp['screw_tip'][1] - kp['head_superior'][1]) / sup_to_inf_y
    else:
        y_ratio = 0.5
    
    if y_ratio < 0.33:
        y_zone = 'superior'
    elif y_ratio < 0.67:
        y_zone = 'central'
    else:
        y_zone = 'inferior'
    
    cleveland_zone = f"{y_zone}_{x_zone}"
    
    # Parker AP (vida-femur eksen kesisimi)
    parker_intersect = line_line_intersection(
        tuple(kp['neck_distal']), tuple(kp['screw_tip']),
        tuple(kp['head_superior']), tuple(kp['head_inferior'])
    )
    
    if parker_intersect:
        sup_y = kp['head_superior'][1]
        inf_y = kp['head_inferior'][1]
        if abs(inf_y - sup_y) > 1:
            parker_ap_ratio = (parker_intersect[1] - sup_y) / (inf_y - sup_y)
        else:
            parker_ap_ratio = 0.5
    else:
        parker_ap_ratio = y_ratio
        parker_intersect = (float(kp['screw_tip'][0]), float(kp['screw_tip'][1]))
    
    parker_ml_ratio = x_ratio
    parker_ratio = parker_ap_ratio
    
    return {
        'TAD_AP_mm': round(tad_ap_final, 2),
        'TAD_AP_baumgaertner_mm': round(tad_ap_baumgaertner, 2),
        'TAD_AP_pixel_calibrated_mm': round(tad_ap_pixel_based, 2),
        'NSA_deg': round(nsa, 2),
        'Cleveland_zone': cleveland_zone,
        'Parker_ratio': round(parker_ratio, 3),
        'Parker_AP_ratio': round(parker_ap_ratio, 3),
        'Parker_ML_ratio': round(parker_ml_ratio, 3),
        'Parker_intersection_point': [float(round(parker_intersect[0], 2)), float(round(parker_intersect[1], 2))],
        'femur_head_diameter_measured_mm': round(d_ap_measured_mm, 2),
        'femur_head_diameter_assumed_mm': D_true_mm,
        'apex_point': [float(round(apex[0], 2)), float(round(apex[1], 2))],
        'x_ap_pixel': round(x_ap_pixel, 2),
        'apex_method': method,
    }


def calculate_failure_risk(params):
    """Failure risk skoru (0-100)"""
    score = 0
    risk_factors = []
    
    tad = params['TAD_AP_mm']
    if tad > 15:
        score += 30
        risk_factors.append(f"TAD-AP>15mm ({tad}mm) - cut-out riski")
    elif tad > 10:
        score += 15
        risk_factors.append(f"TAD-AP 10-15mm ({tad}mm) - sinirda")
    
    nsa = params['NSA_deg']
    if nsa < 120:
        score += 25
        risk_factors.append(f"NSA<120 ({nsa}) - varus")
    elif nsa > 140:
        score += 10
        risk_factors.append(f"NSA>140 ({nsa}) - valgus")
    
    cz = params['Cleveland_zone']
    if 'superior' in cz:
        score += 20
        risk_factors.append(f"Superior zon ({cz}) - cut-out predispozisyonu")
    elif 'inferior' in cz:
        score += 5
    
    pr = params['Parker_ratio']
    if pr < 0.4:
        score += 15
        risk_factors.append(f"Parker AP {pr} - SUPERIOR malpozisyon (cut-out riski)")
    elif pr > 0.6:
        score += 10
        risk_factors.append(f"Parker AP {pr} - INFERIOR malpozisyon")
    
    if score >= 50:
        category = "YUKSEK"
    elif score >= 30:
        category = "ORTA"
    elif score >= 15:
        category = "DUSUK"
    else:
        category = "MINIMAL"
    
    return {
        'risk_score': score,
        'category': category,
        'risk_factors': risk_factors,
    }
