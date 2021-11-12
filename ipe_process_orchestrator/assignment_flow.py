import logging
import json
from typing import Any, Dict, List, Optional, Union
from requests.models import Response
from constants import (
    CANVAS_URL_BEGIN, ASSIGNMENT_GROUP_NAME, ASSIGNMENT_NAME)
from api_handler.api_calls import APIHandler
from ipe_process_orchestrator.api_helper import response_none_check

logger = logging.getLogger(__name__)


class IPEAssignmentFlow:

    def __init__(self, api_handler, course_id, rubric_id) -> None:
        self.rubric_id: str = rubric_id
        self.course_id: int = course_id
        self.api_handler: APIHandler = api_handler

    def _look_up_ipe_assignment(self) -> Union[List[int], int]:
        """
        This is the use case for copied course that might have the same IPE assignment/group names as the original course.
        Just look up assignment group by name and then look up the assignment.
        Will be fetching 100 records only and it is highly unlikely that more than 100 assignment groups will there.
        the assignment groups will also bring in assignment names to check and compare.
        """
        lookup_ag_payload: Dict = {'include[]': 'assignments', 'per_page': 100}
        lookup_ag_url: str = f'{CANVAS_URL_BEGIN}/courses/{self.course_id}/assignment_groups'
        lookup_ag_resp: Optional[Response] = self.api_handler.api_call_with_retries(
            lookup_ag_url, 'GET', lookup_ag_payload)

        err_msg: str = f"Error looking up assignment group '{ASSIGNMENT_GROUP_NAME}' with assignment name '{ASSIGNMENT_NAME}' for course {self.course_id} failed"
        response_none_check(lookup_ag_resp, err_msg) 

        lookup_ag_resp_json: List[Dict[str, Any]] = json.loads(lookup_ag_resp.text) #type: ignore
        ag_list: List[int] = list()
        for ag in lookup_ag_resp_json:
            if ag['name'].strip() == ASSIGNMENT_GROUP_NAME:
                for assignment in ag['assignments']:
                    if assignment['name'].strip() == ASSIGNMENT_NAME:
                        self._delete_assignment(assignment['id'])
                ag_list.append(ag['id'])
        return ag_list if not ag_list else ag_list[0]

    def _delete_assignment(self, assignment_id: int) -> None:
        """
        Deleting the copied course assignment
        """
        delete_assignment_url: str = f'{CANVAS_URL_BEGIN}/courses/{self.course_id}/assignments/{assignment_id}'
        delete_assignment_resp: Optional[Response] = self.api_handler.api_call_with_retries(
            delete_assignment_url, 'DELETE')

        err_msg: str = f'Error deleting assignment {assignment_id} for course {self.course_id}'
        response_none_check(delete_assignment_resp, err_msg)

        logging.info(
            f'Deleted assignment: {assignment_id} for course: {self.course_id}')

    def _create_assignment_group(self) -> int:
        """
        Creating an assignment group with name 'IPE Competencies' always and locate at the end of the assignment list
        """
        ag_payload: Dict = {'name': ASSIGNMENT_GROUP_NAME, 'position': 2000}
        assignment_group_creation_url: str = f'{CANVAS_URL_BEGIN}/courses/{self.course_id}/assignment_groups'
        ag_resp: Optional[Response] = self.api_handler.api_call_with_retries(
            assignment_group_creation_url, 'POST', ag_payload)

        err_msg: str = f'Error creating assignment group {ASSIGNMENT_GROUP_NAME} for course {self.course_id}'
        response_none_check(ag_resp, err_msg)

        assignment_group_id: int = json.loads(ag_resp.text)['id'] #type: ignore
        logger.info(
            f'Created assignment group: {assignment_group_id} for course: {self.course_id}')
        return assignment_group_id

    def _create_assignment(self, assignment_group_id: int) -> int:
        """
        Creates an IPE no submission assignment with zero points, don't notify student with name 'IPE Competencies Attained and in IPE Competencies group'
        """
        assignment_payload: Dict = {
            'assignment[name]': ASSIGNMENT_NAME,
            'assignment[description]': 'This assignment is used for applying IPE competencies and does not require any student submissions',
            'assignment[points_possible]': 0,
            'assignment[submission_types][]': 'none',
            'assignment[assignment_group_id]': assignment_group_id,
            'assignment[notify_of_update]': 'false',
            'assignment[published]': 'true',
            'assignment[omit_from_final_grade]': 'true',
            'assignment[grading_type]': 'not_graded'}
        assignment_creation_url: str = f'{CANVAS_URL_BEGIN}/courses/{self.course_id}/assignments'
        assignment_resp: Optional[Response] = self.api_handler.api_call_with_retries(
            assignment_creation_url, 'POST', assignment_payload)

        err_msg: str = f'Error creating assignment for course {self.course_id} failed'
        response_none_check(assignment_resp, err_msg)

        assignment_id: int = json.loads(assignment_resp.text)['id'] #type: ignore
        logger.info(
            f'Created assignment: {assignment_id} in a group: {assignment_group_id} for course: {self.course_id}')
        return assignment_id

    def _assign_ipe_rubrics(self, assignment_id: int) -> None:
        """
        assigning IPE Rubrics to the assignment created from the earlier step. Raises an exception if the rubric is not assigned
        """
        rubrics_payload: Dict = {
            'rubric_association[association_type]': 'Assignment',
            'rubric_association[association_id]': assignment_id,
            'rubric_association[use_for_grading]': 'false',
            'rubric_association[purpose]': 'grading',
            'rubric_association[rubric_id]': self.rubric_id}
        rubrics_creation_url: str = f'{CANVAS_URL_BEGIN}/courses/{self.course_id}/rubric_associations'
        rubrics_resp: Optional[Response] = self.api_handler.api_call_with_retries(
            rubrics_creation_url, 'POST', rubrics_payload)

        err_msg: str = f"Error assigning rubrics {self.rubric_id} for assignment {assignment_id} for course failed {self.course_id}"
        response_none_check(rubrics_resp, err_msg)

        logger.info(f'Rubrics {self.rubric_id} is assigned to assignment {assignment_id} in courses {self.course_id}')

    def start_assignment_flow(self):
        logger.info(
            f'Starting {type(self).__name__}  for course {self.course_id}')
        try:
            assignment_group_id: int = self._look_up_ipe_assignment()
            if not assignment_group_id:
                assignment_group_id = self._create_assignment_group()
            assignment_id: int = self._create_assignment(assignment_group_id)
            self._assign_ipe_rubrics(assignment_id)
            return assignment_id

        except Exception as e:
            raise e
