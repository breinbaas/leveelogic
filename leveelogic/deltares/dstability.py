from pydantic import BaseModel, DirectoryPath, FilePath
import geolib as gl
from pathlib import Path
from shapely.geometry import Polygon, LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from typing import Dict, List, Tuple, Union, BinaryIO, Optional
from dotenv import load_dotenv
import os
import subprocess
from geolib.geometry.one import Point
from geolib.models.dstability.internal import (
    PersistableHeadLine,
    PersistablePoint,
    ShearStrengthModelTypePhreaticLevelInternal,
    UpliftVanParticleSwarmResult,
    BishopBruteForceResult,
    SpencerGeneticAlgorithmResult,
)

from leveelogic.geometry.characteristic_point import (
    CharacteristicPoint,
    CharacteristicPointType,
)
from ..helpers import polyline_polyline_intersections

load_dotenv()
DSTABILITY_MIGRATION_CONSOLE_PATH = os.getenv("DSTABILITY_MIGRATION_CONSOLE_PATH")


class DStability(BaseModel):
    name: str = ""
    characteristic_points: List[CharacteristicPoint] = []
    model: gl.DStabilityModel = gl.DStabilityModel()
    current_scenario_index: int = 0
    current_stage_index: int = 0
    soillayers: List[Dict] = []
    soils: Dict = {}
    points: List[Tuple[float, float]] = []
    boundary: List[Tuple[float, float]] = []
    surface: List[Tuple[float, float]] = []

    @classmethod
    def from_stix(cls, stix_file: str, auto_upgrade=True) -> "DStability":
        """Generate a DStability object from a stix file

        Args:
            stix_file (str): The stix file path

        Returns:
            DStability: A DStability object
        """
        result = DStability()
        result.name = Path(stix_file).stem
        try:
            result.model.parse(Path(stix_file))
        except ValueError as e:
            if str(e) == "Can't listdir a file" and auto_upgrade:
                try:
                    subprocess.run(
                        [DSTABILITY_MIGRATION_CONSOLE_PATH, stix_file, stix_file]
                    )
                    result.model.parse(Path(stix_file))
                except Exception as e:
                    raise e
            else:
                raise e

        result.set_scenario_and_stage(0, 0)
        return result

    @property
    def left(self) -> float:
        """Get the left x coordinate of the current geometry

        Returns:
            float: The left x coordinate of the current geometry
        """
        return min([p[0] for p in self.points])

    @property
    def right(self) -> float:
        """Get the right x coordinate of the current geometry

        Returns:
            float: The right x coordinate of the current geometry
        """
        return max([p[0] for p in self.points])

    @property
    def top(self) -> float:
        """Get the top z coordinate of the current geometry

        Returns:
            float: The top z coordinate of the current geometry
        """
        return max([p[1] for p in self.points])

    @property
    def bottom(self) -> float:
        """Get the bottom z coordinate of the current geometry

        Returns:
            float: The bottom z coordinate of the current geometry
        """
        return min([p[1] for p in self.points])

    @property
    def phreatic_line(self) -> Optional[PersistableHeadLine]:
        """Get the phreatic line object

        Returns:
            Optional[PersistableHeadLine]: The preathic line or None if not set
        """
        waternet = self.model.waternets[
            0
        ]  # [0] is that correct? don't think so! should depend on the current geom
        for headline in waternet.HeadLines:
            if headline.Id == waternet.PhreaticLineId:
                return headline

        return None

    @property
    def phreatic_line_points(self) -> List[Tuple[float, float]]:
        """Get the points of the current phreatic line

        Raises:
            ValueError: Raises an error if no phreatic line is found

        Returns:
            List[Tuple[float, float]]: The points of the phreatic line (x,z)
        """
        pl = self.phreatic_line
        if pl is not None:
            return [(p.X, p.Z) for p in self.phreatic_line.Points]
        else:
            return []

    def get_headline_coordinates(self, label: str) -> List[Tuple[float, float]]:
        """Get the coordinates of the given headline

        Args:
            label (str): The label of the headline

        Returns:
            List[Tuple[float, float]]: List of points of the given headline
        """
        for hl in self.model.waternets[0].HeadLines:
            if hl.Label == label:
                return [(p.X, p.Z) for p in hl.Points]

        raise ValueError(f"Invalid headline label '{label}' (not found)")

    def set_headline_coordinates(self, label: str, coords: List[Tuple[float, float]]):
        """Overwrite the current coordinates (from left to right) of a headline with the given coordinates

        Args:
            label (str): Label of the headline
            coords (List[Tuple[float, float]]): New coordinates
        """
        for hl in self.model.waternets[0].HeadLines:
            if hl.Label == label:
                if len(coords) > len(hl.Points):
                    raise ValueError(
                        f"Trying to set more coords ({len(coords)}) then currently in headline '{label}' ({len(hl.Points)})"
                    )
                for i in range(len(coords)):
                    hl.Points[i] = PersistablePoint(X=coords[i][0], Z=coords[i][1])
                return

        raise ValueError(f"Invalid headline label '{label}' (not found)")

    @property
    def remarks(self) -> str:
        if self.model.datastructure.projectinfo.Remarks is None:
            return ""
        else:
            return self.model.datastructure.projectinfo.Remarks

    @property
    def num_scenarios(self) -> int:
        return len(self.model.scenarios)

    def num_stages(self, scenario_index: int) -> int:
        if scenario_index < len(self.model.scenarios):
            return len(self.model.scenarios[scenario_index].Stages)
        else:
            raise ValueError(f"Invalid scenario index {scenario_index}")

    def stage_label(self, scenario_index: int, stage_index: int) -> str:
        if scenario_index < len(self.model.scenarios):
            if stage_index < len(self.model.scenarios[scenario_index].Stages):
                return self.model.scenarios[scenario_index].Stages[stage_index].Label
            else:
                raise ValueError(f"Invalid stage index {stage_index}")
        else:
            raise ValueError(f"Invalid scenario index {scenario_index}")

    def scenario_label(self, scenario_index: int) -> str:
        if scenario_index < len(self.model.scenarios):
            return self.model.scenarios[0].Label
        raise ValueError(f"Invalid scenario index {scenario_index}")

    def set_phreatic_line(self, points: List[Tuple[float, float]]):
        """Set the phreatic line from the given points

        Args:
            points (List[Tuple[float, float]]): A list of points
        """
        # TODO this is still far from ideal because it leave the old
        # pl line. That has no influence on the result but it looks bad

        self.model.add_head_line(
            [Point(x=p[0], z=p[1]) for p in points],
            "Phreatic line",
            is_phreatic_line=True,
            scenario_index=self.current_scenario_index,
            stage_index=self.current_stage_index,
        )

    def _post_process(self):
        """Do some post processing stuff to set properties and save time"""
        # get the points
        layers = self.model._get_geometry(
            self.current_scenario_index, self.current_stage_index
        ).Layers
        polygons = []
        points = []

        self.soillayers = []
        self.soils = {}
        self.points = []
        self.boundary = []
        self.surface = []

        soilcolors = {
            sv.SoilId: sv.Color[:1] + sv.Color[3:]  # remove the alpha part
            for sv in self.model.datastructure.soilvisualizations.SoilVisualizations
        }

        for soil in self.model.soils.Soils:
            self.soils[soil.Id] = {
                "code": soil.Code,
                "name": soil.Name,
                "color": soilcolors[soil.Id],
                "yd": soil.VolumetricWeightAbovePhreaticLevel,
                "ys": soil.VolumetricWeightBelowPhreaticLevel,
            }

        soillayers = {}
        for sl in self.model.datastructure.soillayers[0].SoilLayers:
            soillayers[sl.LayerId] = sl.SoilId

        for layer in layers:
            points += layer.Points
            polygons.append(Polygon([(p.X, p.Z) for p in layer.Points]))
            self.soillayers.append(
                {
                    "points": [(p.X, p.Z) for p in layer.Points],
                    "soil": self.soils[soillayers[layer.Id]],
                }
            )

        self.points = [(p.X, p.Z) for p in points]

        # now remove the ids of the soils
        self.soils = [d for d in self.soils.values()]

        # get the surface
        # merge all polygons and return the boundary of that polygon
        boundary = orient(unary_union(polygons), sign=-1)

        # get the points
        self.boundary = [
            (round(p[0], 3), round(p[1], 3))
            for p in list(zip(*boundary.exterior.coords.xy))[:-1]
        ]

        # get the leftmost point
        left = min([p[0] for p in self.boundary])
        topleft_point = sorted(
            [p for p in self.boundary if p[0] == left], key=lambda x: x[1]
        )[-1]

        # get the rightmost points
        right = max([p[0] for p in self.boundary])
        rightmost_point = sorted(
            [p for p in self.boundary if p[0] == right], key=lambda x: x[1]
        )[-1]

        # get the index of leftmost point
        idx_left = self.boundary.index(topleft_point)
        self.surface = self.boundary[idx_left:] + self.boundary[:idx_left]

        # get the index of the rightmost point
        idx_right = self.surface.index(rightmost_point)
        self.surface = self.surface[: idx_right + 1]

    def set_characteristic_point(self, x: float, point_type: CharacteristicPointType):
        """Add a characteristic point to the model, this will also check if you are trying to
        add a point that is already in the model. If so it will replace the old one. This only
        applies to points that can only have one in the model

        Args:
            x (float): The x coordinate
            characteristic_point_type (CharacteristicPointType): The type of characteristic point
        """
        # there can only be one of the following types so if this is about them
        # then just change the x value
        if point_type in [
            CharacteristicPointType.TOE_LEFT,
            CharacteristicPointType.CREST_LEFT,
            CharacteristicPointType.REFERENCE_POINT,
            CharacteristicPointType.CREST_RIGHT,
            CharacteristicPointType.TOE_RIGHT,
            CharacteristicPointType.START_POLDER,
            CharacteristicPointType.START_SURFACE,
            CharacteristicPointType.END_SURFACE,
        ]:
            if self.get_characteristic_point(point_type) is not None:
                for i in range(len(self.characteristic_points)):
                    if self.characteristic_points[i].point_type == point_type:
                        self.characteristic_points[i].x = x
            else:
                self.characteristic_points.append(
                    CharacteristicPoint(x=x, point_type=point_type)
                )
        else:
            self.characteristic_points.append(
                CharacteristicPoint(x=x, point_type=point_type)
            )

    def get_characteristic_point(
        self, point_type: CharacteristicPointType
    ) -> Optional[Union[CharacteristicPoint, List[CharacteristicPoint]]]:
        """Get a (list of) characteristic points on this model based on the given point type, if the type is of
        toe left, toe right, crest left, crest right, reference point, start polder, start and end surface
        the result is a single point, all other points can be lists. If no point(s) is / are found the result will be None

        Args:
            characteristic_point_type (CharacteristicPointType): The type of characteristic point

        Returns:
           Optional[Union[CharacteristicPoint, List[CharacteristicPoint]]]: A list with the points or a single point or None
        """
        result = None
        if point_type in [
            CharacteristicPointType.TOE_LEFT,
            CharacteristicPointType.CREST_LEFT,
            CharacteristicPointType.REFERENCE_POINT,
            CharacteristicPointType.CREST_RIGHT,
            CharacteristicPointType.TOE_RIGHT,
            CharacteristicPointType.START_POLDER,
            CharacteristicPointType.START_SURFACE,
            CharacteristicPointType.END_SURFACE,
        ]:
            for cp in self.characteristic_points:
                if cp.point_type == point_type:
                    result = cp
                    break
        else:
            result = [
                cp for cp in self.characteristic_points if cp.point_type == point_type
            ]
            if result == []:
                result = None

        return result

    def surface_intersections(
        self, polyline: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        return polyline_polyline_intersections(polyline, self.surface)

    def surface_points_between(
        self, left: float, right: float
    ) -> List[Tuple[float, float]]:
        """Get a list of surface points between the given limits

        Args:
            left (float): The left limit
            right (float): The right limit

        Returns:
            List[Tuple[float, float]]: List of surface points between left and right
        """
        return [p for p in self.surface if p[0] >= left and p[0] <= right]

    def set_scenario_and_stage(self, scenario_index: int, stage_index: int):
        """Set the current scenario and stage

        Args:
            scenario_index (int): The scenario index
            stage_index (int): The stage index

        Raises:
            ValueError: Raises an error if the scenario index or stage index is / are invalid
        """
        if scenario_index < len(self.model.scenarios):
            self.current_scenario_index = scenario_index
        else:
            raise ValueError(f"Trying to set an invalid scenario index")

        if stage_index < len(self.model.scenarios[self.current_scenario_index].Stages):
            self.current_stage_index = stage_index
        else:
            raise ValueError(
                f"Trying to set an invalid stage index for scenario {self.current_scenario_index}"
            )

        self._post_process()

    def z_at(self, x, scenario_index: int = 0, stage_index: int = 0) -> List[float]:
        """Get a list of z coordinates from intersections with the soillayers on coordinate x

        Args:
            x (_type_): The x coordinate
            scenario_index (int, optional): The scenario index. Defaults to 0.
            stage_index (int, optional): The stage index. Defaults to 0.

        Returns:
            List[float]: A list of intersections sorted from high to low
        """
        layers = self.model._get_geometry(scenario_index, stage_index).Layers
        result, zs = [], []
        for layer in layers:
            for i in range(1, len(layer.Points)):
                p1 = layer.Points[i - 1]
                if i == len(layer.Points):
                    p2 = layer.Points[0]
                else:
                    p2 = layer.Points[i]

                if min(p1.X, p2.X) <= x and x <= max(p1.X, p2.X):
                    if p1.X == p2.X:
                        zs.append(p1.Z)
                    else:
                        zs.append(p1.Z + (x - p1.X) / (p2.X - p1.X) * (p2.Z - p1.Z))

        for r in zs:
            if not r in result:
                result.append(r)

        return sorted(result, reverse=True)

    def has_soilcode(self, soilcode: str) -> bool:
        """Check if the current model has the given soilcode

        Args:
            soilcode (str): The soilcode to check for

        Returns:
            bool: True if the soilcode is available
        """
        return soilcode in [d["code"] for d in self.soils]

    def serialize(self, location: Union[FilePath, DirectoryPath, BinaryIO]):
        """Serialize the model to a file

        Args:
            location (Union[FilePath, DirectoryPath, BinaryIO]): The path to save to
        """
        self.model.serialize(location)

    def extract_soilparameters(self) -> List[str]:
        result = [
            "name,code,model,yd,ys,probabilistic,cohesion,friction angle,dilatancy,S,m\n"
        ]
        for soil in self.model.soils.Soils:
            d = {
                "name": soil.Name,
                "code": soil.Code,
                "model": "",
                "yd": f"{soil.VolumetricWeightAbovePhreaticLevel:.2f}",
                "ys": f"{soil.VolumetricWeightBelowPhreaticLevel:.2f}",
                "prob": "",
                "c": "",
                "phi": "",
                "dilatancy": "",
                "S": "",
                "m": "",
            }

            if soil.IsProbabilistic:
                d["prob"] = "true"
            else:
                ssma = soil.ShearStrengthModelTypeAbovePhreaticLevel
                ssmb = soil.ShearStrengthModelTypeBelowPhreaticLevel

                if (
                    ssma
                    == ShearStrengthModelTypePhreaticLevelInternal.MOHR_COULOMB_ADVANCED
                ):
                    d["model"] = "MOHR_COULOMB_ADVANCED"
                    d[
                        "c"
                    ] = f"{soil.MohrCoulombAdvancedShearStrengthModel.Cohesion:.2f}"
                    d[
                        "phi"
                    ] = f"{soil.MohrCoulombAdvancedShearStrengthModel.FrictionAngle:.2f}"
                    d[
                        "dilatancy"
                    ] = f"{soil.MohrCoulombAdvancedShearStrengthModel.Dilatancy:.2f}"
                elif (
                    ssma
                    == ShearStrengthModelTypePhreaticLevelInternal.MOHR_COULOMB_CLASSIC
                ):
                    d["model"] = "MOHR_COULOMB_CLASSIC"
                    d["c"] = f"{soil.MohrCoulombClassicShearStrengthModel.Cohesion:.2f}"
                    d[
                        "phi"
                    ] = f"{soil.MohrCoulombClassicShearStrengthModel.FrictionAngle:.2f}"
                elif ssma == ShearStrengthModelTypePhreaticLevelInternal.NONE:
                    d["model"] = "NONE"
                elif ssma == ShearStrengthModelTypePhreaticLevelInternal.SU:
                    d["model"] = "SU"
                    d["S"] = f"{soil.SuShearStrengthModel.ShearStrengthRatio:.2f}"
                    d["m"] = f"{soil.SuShearStrengthModel.StrengthIncreaseExponent:.2f}"
                elif ssma == ShearStrengthModelTypePhreaticLevelInternal.SUTABLE:
                    d["model"] = "SUTABLE"
            result.append(
                f"{d['name']},{d['code']},{d['model']},{d['yd']},{d['ys']},{d['prob']},{d['c']},{d['phi']},{d['dilatancy']},{d['S']},{d['m']}\n"
            )
        return result

    def safety_factor_to_dict(self, scenario_index: int = 0, stage_index: int = 0):
        try:
            sf = self.model.get_result(scenario_index, stage_index)
        except Exception as e:
            return {}

        if type(sf) == UpliftVanParticleSwarmResult:
            return {
                "model": "upliftvan_particle_swarm",
                "fos": sf.FactorOfSafety,
                "left_circle": {
                    "x": sf.LeftCenter.X,
                    "z": sf.LeftCenter.Z,
                },
                "right_circle": {
                    "x": sf.RightCenter.X,
                    "z": sf.RightCenter.Z,
                },
                "tangent": sf.TangentLine,
            }
        elif type(sf) == BishopBruteForceResult:
            return {
                "model": "bishop_brute_force",
                "fos": sf.FactorOfSafety,
                "circle": {
                    "x": sf.Circle.Center.X,
                    "z": sf.Circle.Center.Z,
                    "r": sf.Circle.Radius,
                },
            }
        elif type(sf) == SpencerGeneticAlgorithmResult:
            return {
                "model": "spencer_genetic_algorithm",
                "fos": sf.FactorOfSafety,
                "slip_plane": [{"x": p.X, "z": p.Z} for p in sf.SlipPlane],
            }
        else:
            raise ValueError(
                f"Cannot convert the result of type '{type(sf) }' yet, for now limited to spencer genetic, bishop brute force, uplift particlr swarm"
            )
