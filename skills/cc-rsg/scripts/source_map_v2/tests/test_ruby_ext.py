"""M4 acceptance: Ruby/Rails extractor role-types by the 14-unit catalogue."""

from __future__ import annotations

import pytest

from source_map_v2 import extractors
from source_map_v2.model import IdFactory

pytestmark = pytest.mark.skipif(
    extractors.get_extractor("ruby") is None,
    reason="tree-sitter (ruby grammar) not installed",
)

CONTROLLER = '''\
class IssuesController < ApplicationController
  def index
  end
  def show
  end
end
'''

MODEL = "class Issue < ApplicationRecord\nend\n"
JOB = "class MailJob < ApplicationJob\n  def perform\n  end\nend\n"
ROUTES = '''\
Rails.application.routes.draw do
  resources :issues
  namespace :admin do
    resources :users
  end
  get "/health", to: "system#health"
  root "home#index"
end
'''


def _ext(src, path):
    return extractors.get_extractor("ruby").extract(path, src, IdFactory())


def test_controller_and_actions():
    units = _ext(CONTROLLER, "app/controllers/issues_controller.rb")
    ctrl = [u for u in units if u.kind == "rails_controller"]
    actions = [u for u in units if u.kind == "rails_action"]
    assert ctrl and ctrl[0].name == "IssuesController" and ctrl[0].role == "class"
    assert {a.name for a in actions} == {"IssuesController#index", "IssuesController#show"}
    assert all(a.role == "endpoint" for a in actions)


def test_model_path_typing():
    units = _ext(MODEL, "app/models/issue.rb")
    assert any(u.kind == "rails_model" and u.role == "model" and u.name == "Issue" for u in units)


def test_job_path_typing():
    units = _ext(JOB, "app/jobs/mail_job.rb")
    assert any(u.kind == "rails_job" and u.role == "job" for u in units)


def test_routes_groups_and_single():
    units = _ext(ROUTES, "config/routes.rb")
    kinds = [u.kind for u in units]
    assert "rails_route" in kinds          # resources/namespace -> route_group
    groups = [u for u in units if u.kind == "rails_route"]
    assert any("issues" in u.name for u in groups)
    singles = [u for u in units if u.kind == "rails_action" and u.endpoint]
    methods = {u.endpoint["method"] for u in singles}
    assert "GET" in methods                 # get "/health" + root


CONTROLLER_PRIVATE = '''\
class PostsController < ApplicationController
  before_action :set_post
  def index
  end
  def show
  end
  private
  def set_post
  end
  def authorize!
  end
end
'''


def test_private_filters_excluded_from_actions():
    units = _ext(CONTROLLER_PRIVATE, "app/controllers/posts_controller.rb")
    actions = {u.name for u in units if u.kind == "rails_action"}
    assert actions == {"PostsController#index", "PostsController#show"}
    assert "PostsController#set_post" not in actions   # private filter excluded
    assert "PostsController#authorize!" not in actions


def test_draw_wrapper_not_a_route_group():
    units = _ext(ROUTES, "config/routes.rb")
    assert not any(u.name == "draw:draw" for u in units)   # wrapper noise removed


def test_generic_ruby_outside_rails_dirs():
    units = _ext("class Plain\nend\n", "lib_scripts/plain.rb")
    assert any(u.kind == "ruby_class" and u.role == "class" for u in units)
