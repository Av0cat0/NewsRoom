from newsroom.main import load_config
from newsroom.scoring import build_signal
from newsroom.tase import open_articles, upcoming_articles

CFG = load_config()


def up(*items):
    return {"getUpcomingOfferingData": {"result": list(items)}}


def item(name, new, sec, **kw):
    return {"mayaReportId": 1, "companyName": name, "isTheCompanyNew": new, "draftTitle": kw.get("draft"),
            "linkToProspectus": None, "newCompanyType": kw.get("nct"),
            "securitiesTypes": [{"securityType": s} for s in sec]}


def sig(article):
    return build_signal(article, CFG)


def test_new_equity_company_is_an_instant_ipo():
    (a,) = upcoming_articles(up(item("ACME", True, ["Share", "Warrant"], draft="Draft Prospectus")), 1.2)
    s = sig(a)
    assert s.event_type == "ipo" and s.tier == "instant"
    assert "ACME" in a.title and "Draft Prospectus" in a.title


def test_follow_on_equity_goes_to_digest():
    (a,) = upcoming_articles(up(item("OLDCO", False, ["Share"])), 1.2)
    assert sig(a).tier == "digest"


def test_bond_offerings_stay_quiet():
    arts = upcoming_articles(up(item("BANK", False, ["Bond"]), item("NEWBOND", True, ["Bond"], nct="New Bond Company"),
                                item("CONV", False, ["Convertible Bond"])), 1.2)
    assert all(sig(a).tier == "log" for a in arts)


def test_stage_change_gives_a_new_article_id():
    a1, = upcoming_articles(up(item("ACME", True, ["Share"], draft="Draft Prospectus")), 1.2)
    a2, = upcoming_articles(up(item("ACME", True, ["Share"], draft="Prospectus for Completion")), 1.2)
    assert a1.uid != a2.uid


def test_open_equity_offering():
    data = {"getOpenOfferingData": {"result": [
        {"issuerName": "ACME", "isTheCompanyNew": False, "offeringType": "Price", "offerNumber": 7,
         "offerEndsAt": "2026-11-20T16:30:00", "linkToOfferReport": None,
         "securities": [{"securityFullTypeCode": "0101"}]},
        {"issuerName": "BANK", "isTheCompanyNew": False, "offeringType": "Uniform Proposal", "offerNumber": 8,
         "offerEndsAt": "2026-11-20T16:30:00", "linkToOfferReport": None,
         "securities": [{"securityFullTypeCode": "0501"}]}]}}
    eq, bond = open_articles(data, 1.2)
    assert sig(eq).tier == "digest" or sig(eq).tier == "instant"
    assert sig(bond).tier == "log"
