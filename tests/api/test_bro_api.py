from leveelogic.api.bro_api import BROAPI


class TestBROAPI:
    def test__get_cpt_metadata_by_bounds(self):
        api = BROAPI()
        cpt_characteristics = api._get_cpt_metadata_by_bounds(
            left=52.128694, bottom=4.608265, right=52.13233, top=4.622127
        )
        assert len(cpt_characteristics) > 0

    def test__get_cpt_metadata_by_bounds_limited(self):
        api = BROAPI()
        cpt_characteristics = api._get_cpt_metadata_by_bounds(
            left=52.128694, bottom=4.608265, right=52.13233, top=4.622127, max_num=3
        )
        assert len(cpt_characteristics) == 3

    def test_get_cpts_by_bounds(self):
        api = BROAPI()
        cpts_strings, cpts = api.get_cpts_by_bounds(
            left=52.128694, bottom=4.608265, right=52.13233, top=4.622127, max_num=1
        )
        assert len(cpts) == 1
        assert len(cpts_strings) == 1

    def test__get_cpt_metadata_by_bounds_exclude_bro_ids(self):
        api = BROAPI()
        cpt_characteristics_o = api._get_cpt_metadata_by_bounds(
            left=52.128694,
            bottom=4.608265,
            right=52.13233,
            top=4.622127,
        )
        cpt_characteristics_f = api._get_cpt_metadata_by_bounds(
            left=52.128694,
            bottom=4.608265,
            right=52.13233,
            top=4.622127,
            exclude_bro_ids=["BRO_CPT000000160452"],
        )
        assert len(cpt_characteristics_o) == len(cpt_characteristics_f) + 1
